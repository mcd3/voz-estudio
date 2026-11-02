import asyncio
import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from . import storage as store
from .audio import MP3Encoder
from .engine import Engine, prepare_voice

engine = Engine()
registration_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='voices')
generation_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='speech')
cancel_flags = {}
jobs_lock = threading.Lock()


def prepare_engine():
    try:
        engine.load()
    except Exception:
        logging.exception('No se ha podido preparar el motor al iniciar.')


@asynccontextmanager
async def lifespan(app):
    store.recover_interrupted()
    engine.state = 'loading'
    # Use the generation queue so requests cannot load the model concurrently.
    generation_pool.submit(prepare_engine)
    yield
    with jobs_lock:
        for flag in cancel_flags.values():
            flag.set()


app = FastAPI(title='Voz Estudio', version=__version__, lifespan=lifespan)
app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')


@app.exception_handler(FileNotFoundError)
async def missing(request, exc):
    return JSONResponse({'detail': 'No se ha encontrado el elemento.'}, status_code=404)


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)


@app.middleware('http')
async def local_origin(request, call_next):
    # This unauthenticated application is intentionally bound to loopback.
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        from urllib.parse import urlsplit
        if origin and urlsplit(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail': 'Origen no permitido.'}, status_code=403)
    return await call_next(request)


@app.get('/')
def index():
    return FileResponse(Path(__file__).parent / 'static' / 'index.html', headers={'Cache-Control': 'no-store'})


@app.get('/api/status')
def status():
    with jobs_lock:
        pending = len(cancel_flags)
    return {'app': 'voz-estudio', 'pid': os.getpid(), 'instance': os.environ.get('VOZ_INSTANCE', ''),
            'version': __version__, 'engine': engine.state, 'device': engine.mode, 'error': engine.error,
            'pending_jobs': pending, 'voices': len(store.voices()), 'recordings': len(store.records())}


@app.get('/api/voices')
def list_voices():
    return store.voices()


@app.post('/api/voices', status_code=202)
async def register_voice(name: str = Form(...), audio: UploadFile = File(...)):
    name = name.strip()
    if not 1 <= len(name) <= 80:
        raise HTTPException(422, 'Escribe un nombre de entre 1 y 80 caracteres.')
    identifier = uuid.uuid4().hex
    path = store.voice_path(identifier)
    path.parent.mkdir(parents=True)
    destination = path.parent / 'original.audio'
    size = 0
    try:
        with destination.open('wb') as output:
            while chunk := await audio.read(1024 * 1024):
                size += len(chunk)
                if size > 50 * 1024 * 1024:
                    raise HTTPException(413, 'El archivo no puede superar los 50 MB.')
                output.write(chunk)
        if not size:
            raise HTTPException(422, 'El archivo está vacío.')
        voice = {'schema_version': 1, 'id': identifier, 'name': name, 'slug': store.slug(name),
                 'created_at': store.now().isoformat(), 'status': 'queued', 'error': None,
                 'transcript': '', 'duration_s': None, 'original_filename': Path(audio.filename or 'audio').name}
        store.write_json(path, voice)
        registration_pool.submit(prepare_voice, identifier)
        return voice
    except BaseException:
        if not path.exists():
            destination.unlink(missing_ok=True)
            path.parent.rmdir()
        raise
    finally:
        await audio.close()


@app.post('/api/voices/{identifier}/retry', status_code=202)
def retry_voice(identifier: str):
    path = store.voice_path(identifier)
    with store.LOCK:
        voice = store.read_json(path)
        if voice['status'] != 'error':
            raise HTTPException(409, 'Esta voz no necesita reintento.')
        store.update(path, status='queued', error=None)
    registration_pool.submit(prepare_voice, identifier)
    return {'id': identifier, 'status': 'queued'}


@app.get('/api/voices/{identifier}/reference')
def reference(identifier: str):
    voice = store.read_json(store.voice_path(identifier))
    if voice['status'] != 'ready':
        raise HTTPException(409, 'La referencia todavía no está preparada.')
    return FileResponse(store.voice_path(identifier).parent / 'reference.wav', media_type='audio/wav')


class GenerateRequest(BaseModel):
    voice_id: str
    text: str = Field(min_length=1, max_length=50000)


def perform_generation(identifier, flag):
    path = store.record_path(identifier)
    record = store.read_json(path)
    encoder = None
    start = time.perf_counter()
    final_status, error = 'completed', None
    first = None
    try:
        if flag.is_set():
            raise InterruptedError('Generación cancelada.')
        store.update(path, status='loading', started_at=store.now().isoformat())
        engine.load()
        prepared = time.perf_counter() - start
        store.update(path, status='generating', device=engine.mode, model_preparation_s=round(prepared, 3))
        voice = store.read_json(store.voice_path(record['voice_id']))
        with path.with_suffix('.mp3').open('wb') as output:
            try:
                for samples, sr, _timing in engine.generate(record['text'], voice):
                    if flag.is_set():
                        raise InterruptedError('Generación cancelada. Se conserva el audio parcial si existe.')
                    if encoder is None:
                        encoder = MP3Encoder(sr)
                    data = encoder.encode(samples)
                    if data:
                        output.write(data)
                        output.flush()
                        elapsed = time.perf_counter() - start
                        if first is None:
                            first = elapsed
                        store.update(path, first_audio_s=round(first, 3), elapsed_s=round(elapsed, 3),
                                     audio_duration_s=round(encoder.samples / encoder.sr, 3), audio_bytes=output.tell())
            finally:
                if encoder is not None:
                    output.write(encoder.finish())
                    output.flush()
        if encoder is None or not encoder.samples:
            raise RuntimeError('El modelo no ha devuelto audio.')
    except InterruptedError as exc:
        final_status, error = 'cancelled', str(exc)
    except Exception as exc:
        logging.exception('Fallo de generación %s', identifier)
        final_status, error = 'error', str(exc)
    finally:
        audio = path.with_suffix('.mp3')
        try:
            store.update(path, status=final_status, error=error, finished_at=store.now().isoformat(),
                         processing_s=round(time.perf_counter() - start, 3), first_audio_s=round(first, 3) if first else None,
                         audio_duration_s=round(encoder.samples / encoder.sr, 3) if encoder else 0,
                         audio_bytes=audio.stat().st_size if audio.exists() else 0)
        finally:
            with jobs_lock:
                cancel_flags.pop(identifier, None)


@app.post('/api/recordings', status_code=202)
def create_recording(request: GenerateRequest):
    voice = store.read_json(store.voice_path(request.voice_id))
    if voice['status'] != 'ready':
        raise HTTPException(409, 'Espera a que la voz esté preparada.')
    text = request.text.strip()
    if not text:
        raise HTTPException(422, 'Escribe el texto que quieres convertir en audio.')
    with jobs_lock:
        if len(cancel_flags) >= 5:
            raise HTTPException(429, 'La cola está llena. Espera a que termine algún audio.')
        identifier = uuid.uuid4().hex
        timestamp = store.now()
        filename = f"{voice['slug']}_{timestamp:%Y-%m-%d_%H-%M-%S}_{identifier}"
        record = {'schema_version': 1, 'id': identifier, 'voice_id': voice['id'], 'voice_name': voice['name'],
                  'created_at': timestamp.isoformat(), 'text': text, 'characters': len(text), 'status': 'queued',
                  'filename': filename + '.mp3', 'metadata_filename': filename + '.json',
                  'engine': 'Qwen3-TTS-12Hz-0.6B-Base', 'error': None, 'audio_bytes': 0,
                  'audio_duration_s': 0, 'first_audio_s': None, 'processing_s': None}
        store.write_json(store.folder('recordings') / (filename + '.json'), record)
        flag = threading.Event()
        cancel_flags[identifier] = flag
        generation_pool.submit(perform_generation, identifier, flag)
    return record


@app.get('/api/recordings')
def list_recordings(q: str = '', voice_id: str = '', offset: int = 0, limit: int = 50):
    items = store.records()
    if voice_id:
        store.valid_id(voice_id)
        items = [r for r in items if r['voice_id'] == voice_id]
    if q.strip():
        query = q.casefold().strip()
        items = [r for r in items if query in (r['text'] + ' ' + r['voice_name']).casefold()]
    return {'total': len(items), 'items': items[max(offset, 0):max(offset, 0) + min(max(limit, 1), 100)]}


@app.get('/api/recordings/{identifier}')
def get_recording(identifier: str):
    return store.read_json(store.record_path(identifier))


@app.post('/api/recordings/{identifier}/cancel')
def cancel_recording(identifier: str):
    store.record_path(identifier)
    with jobs_lock:
        flag = cancel_flags.get(identifier)
        if flag is None:
            raise HTTPException(409, 'La generación ya ha terminado.')
        flag.set()
    return {'status': 'cancelling'}


@app.get('/api/recordings/{identifier}/audio')
def audio_file(identifier: str, download: bool = False):
    path = store.record_path(identifier)
    record = store.read_json(path)
    if record['status'] not in ('completed', 'cancelled', 'error') or not record.get('audio_bytes'):
        raise HTTPException(409, 'El audio todavía no está disponible.')
    return FileResponse(path.with_suffix('.mp3'), media_type='audio/mpeg',
                        filename=record['filename'] if download else None)


@app.get('/api/recordings/{identifier}/json')
def record_json(identifier: str):
    path = store.record_path(identifier)
    return JSONResponse(store.read_json(path), headers={'Content-Disposition': f'attachment; filename="{path.name}"'})


@app.get('/api/recordings/{identifier}/stream')
async def stream_audio(identifier: str):
    path = store.record_path(identifier)

    async def chunks():
        position = 0
        while True:
            audio = path.with_suffix('.mp3')
            if audio.exists():
                with audio.open('rb') as f:
                    f.seek(position)
                    data = f.read(65536)
                if data:
                    position += len(data)
                    yield data
                    continue
            if store.read_json(path)['status'] in ('completed', 'error', 'cancelled'):
                break
            await asyncio.sleep(0.1)
    return StreamingResponse(chunks(), media_type='audio/mpeg', headers={'Cache-Control': 'no-store'})


@app.get('/api/export')
def export():
    return JSONResponse({'schema_version': 1, 'exported_at': store.now().isoformat(),
                         'voices': store.voices(), 'recordings': store.records()},
                        headers={'Content-Disposition': 'attachment; filename="voz-estudio-historial.json"'})
