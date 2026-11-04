import asyncio
import json
import logging
import os
import threading
import time
import uuid
import shutil
import subprocess
import sys
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
from .design_worker import DESIGN_MODEL, model_path as design_model_path
from .catalog import MODELS, LANGUAGES, SPEAKERS, model_path, validate

engine = Engine()
registration_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='voices')
generation_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='speech')
cancel_flags = {}
jobs_lock = threading.RLock()
design_jobs = set()
design_processes = set()
shutting_down = threading.Event()


def prepare_engine():
    try:
        engine.load()
    except Exception:
        logging.exception('No se ha podido preparar el motor al iniciar.')


@asynccontextmanager
async def lifespan(app):
    shutting_down.clear()
    store.recover_interrupted()
    for path in store.folder('designs').glob('*/design.json'):
        if store.read_json(path)['status'] in ('queued','designing'):
            store.update(path,status='error',error='El diseño se interrumpió al cerrar la aplicación. Crea una muestra nueva.')
    engine.state = 'loading'
    # Use the generation queue so requests cannot load the model concurrently.
    generation_pool.submit(prepare_engine)
    yield
    shutting_down.set()
    with jobs_lock:
        for flag in cancel_flags.values():
            flag.set()
        children=list(design_processes)
    for child in children:
        if child.poll() is None:
            child.terminate()


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
        pending = len(cancel_flags) + len(design_jobs)
    return {'app': 'voz-estudio', 'pid': os.getpid(), 'instance': os.environ.get('VOZ_INSTANCE', ''),
            'version': __version__, 'engine': engine.state, 'device': engine.mode, 'error': engine.error,
            'loaded_model': getattr(engine,'model_key',None),
            'pending_jobs': pending, 'design_model_available': design_model_path(store.MODEL_CACHE) is not None,
            'voices': len(store.voices()), 'recordings': len(store.records())}


def design_path(identifier):
    return store.folder('designs')/store.valid_id(identifier)/'design.json'


class SpeechSettings(BaseModel):
    language: str = 'Spanish'
    seed: int = Field(default=42,ge=0,le=4294967295)
    temperature: float = Field(default=.9,ge=.1,le=2)
    top_p: float = Field(default=1.,gt=0,le=1)
    top_k: int = Field(default=50,ge=0,le=100)
    repetition_penalty: float = Field(default=1.05,ge=.5,le=2)
    do_sample: bool = True
    max_new_tokens: int = Field(default=1200,ge=128,le=2048)


@app.get('/api/catalog')
def catalog():
    return {'models':[{**item,'id':key,'available':model_path(store.MODEL_CACHE,key) is not None}
                      for key,item in MODELS.items()], 'languages':LANGUAGES,'speakers':SPEAKERS}


class DesignRequest(SpeechSettings):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default='',max_length=1500)
    text: str = Field(min_length=30, max_length=390)
    model: str = 'design17'
    speaker: str = 'Ryan'
    max_new_tokens: int = Field(default=600,ge=128,le=1200)


def perform_design(identifier):
    path=design_path(identifier)
    try:
        engine.unload()
        engine.state='designing'
        store.update(path,status='designing',error=None)
        arguments=[sys.executable,'-B','-m','voz_estudio.design_worker','--folder',str(path.parent),'--cache',str(store.MODEL_CACHE)]
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        with (path.parent/'worker.log').open('ab') as log:
            if shutting_down.is_set():raise InterruptedError('La aplicación se está cerrando.')
            with subprocess.Popen(arguments,stdout=log,stderr=log,creationflags=flags) as child:
                with jobs_lock:
                    design_processes.add(child)
                    if shutting_down.is_set():child.terminate()
                try:
                    try:
                        result=child.wait(timeout=900)
                    except subprocess.TimeoutExpired:
                        child.kill();child.wait()
                        raise RuntimeError('La creación ha superado el tiempo máximo.')
                    if result:raise RuntimeError('El proceso del modelo ha terminado con un error.')
                finally:
                    with jobs_lock:design_processes.discard(child)
        if store.read_json(path)['status']!='ready':
            raise RuntimeError('El modelo no ha terminado la muestra.')
    except Exception as exc:
        logging.exception('Fallo al diseñar voz %s',identifier)
        store.update(path,status='error',error='No se ha podido crear la muestra. '+str(exc)+' Consulta worker.log en la carpeta de este diseño.')
    finally:
        if not shutting_down.is_set():
            engine.state='loading'
            prepare_engine()
        with jobs_lock:
            design_jobs.discard(identifier)


@app.post('/api/designs',status_code=202)
def create_design(request: DesignRequest):
    values={k:v.strip() if isinstance(v,str) else v for k,v in request.model_dump().items()}
    spec=validate(request.model,request.language,request.speaker,request.description,('design','custom'))
    if not values['name'] or (spec['kind']=='design' and len(values['description'])<10) or len(values['text'])<30:
        raise HTTPException(422,'Completa el nombre, la descripción y el texto de muestra.')
    if model_path(store.MODEL_CACHE,request.model) is None:
        raise HTTPException(409,'Falta '+spec['label']+'. Ejecuta Instalar-Modelos-Qwen.cmd.')
    with jobs_lock:
        if len(cancel_flags)+len(design_jobs)>=5:
            raise HTTPException(429,'La cola está llena. Espera a que termine un trabajo.')
        identifier=uuid.uuid4().hex
        job=dict(schema_version=1,id=identifier,created_at=store.now().isoformat(),status='queued',
                 model_repo=spec['repo'],error=None,voice_id=None,**values)
        store.write_json(design_path(identifier),job)
        design_jobs.add(identifier)
        generation_pool.submit(perform_design,identifier)
    return job


@app.get('/api/designs')
def list_designs():
    with store.LOCK:
        return sorted((store.read_json(p) for p in store.folder('designs').glob('*/design.json')),
                      key=lambda d:d['created_at'],reverse=True)[:50]


@app.get('/api/designs/{identifier}')
def get_design(identifier: str):
    return store.read_json(design_path(identifier))


@app.get('/api/designs/{identifier}/audio')
def design_audio(identifier: str):
    path=design_path(identifier)
    if store.read_json(path)['status']!='ready':
        raise HTTPException(409,'La muestra todavía no está preparada.')
    return FileResponse(path.parent/'preview.wav',media_type='audio/wav')


@app.post('/api/designs/{identifier}/save')
def save_design(identifier: str):
    path=design_path(identifier)
    with store.LOCK:
        job=store.read_json(path)
        if job['status']!='ready':
            raise HTTPException(409,'Espera a que termine la muestra antes de guardarla.')
        if job.get('voice_id'):
            return store.read_json(store.voice_path(job['voice_id']))
        voice_id=uuid.uuid4().hex
        target=store.voice_path(voice_id)
        target.parent.mkdir(parents=True)
        try:
            for filename in ('original.audio','reference.wav'):
                shutil.copyfile(path.parent/'preview.wav',target.parent/filename)
            (target.parent/'reference.txt').write_text(job['text'],encoding='utf-8')
            voice=dict(schema_version=1,id=voice_id,name=job['name'],slug=store.slug(job['name']),
                       created_at=store.now().isoformat(),ready_at=store.now().isoformat(),status='ready',error=None,
                       transcript=job['text'],duration_s=job['duration_s'],original_duration_s=job['duration_s'],
                       original_filename='qwen-sample.wav',origin='voice_design',design_model=job.get('model_repo',DESIGN_MODEL),
                       language=job.get('language','Spanish'),speaker=job.get('speaker'),seed=job.get('seed'),
                       description=job['description'],source_design_id=identifier)
            store.write_json(target,voice)
            store.update(path,voice_id=voice_id)
        except Exception:
            # A failed save stays retryable; leave the preview untouched.
            raise
    return voice


@app.get('/api/voices')
def list_voices():
    return store.voices()


@app.post('/api/voices', status_code=202)
async def register_voice(name: str = Form(...), audio: UploadFile = File(...), language: str = Form('Auto')):
    name = name.strip()
    if language not in LANGUAGES:raise HTTPException(422,'Idioma no compatible.')
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
                 'transcript': '', 'duration_s': None, 'language':language, 'original_filename': Path(audio.filename or 'audio').name}
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


class GenerateRequest(SpeechSettings):
    voice_id: str | None = None
    text: str = Field(min_length=1, max_length=50000)
    model: str = 'base06'
    speaker: str = 'Ryan'
    instruct: str = Field(default='',max_length=1500)
    force_reload: bool = False


def perform_generation(identifier, flag):
    path = store.record_path(identifier)
    record = store.read_json(path)
    encoder = None
    start = time.perf_counter()
    final_status, error = 'completed', None
    first = None
    prepared = 0
    try:
        if flag.is_set():
            raise InterruptedError('Generación cancelada.')
        store.update(path, status='loading', started_at=store.now().isoformat())
        if record.get('force_reload'):engine.unload()
        reused=getattr(engine,'model_key',None)==record.get('model','base06')
        memory_stats=getattr(engine,'memory_stats',lambda **kwargs:{})
        memory_stats(reset=True)
        engine.load(record.get('model','base06'))
        prepared = time.perf_counter() - start
        store.update(path, status='generating', device=engine.mode, model_preparation_s=round(prepared, 3),
                     model_reused=reused,model_revision=getattr(engine,'revision',None))
        voice = store.read_json(store.voice_path(record['voice_id'])) if record.get('voice_id') else None
        with path.with_suffix('.mp3').open('wb') as output:
            try:
                for samples, sr, _timing in engine.generate(record['text'], voice, record):
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
            elapsed=time.perf_counter()-start
            duration=encoder.samples/encoder.sr if encoder else 0
            inference=max(0,elapsed-prepared)
            store.update(path, status=final_status, error=error, finished_at=store.now().isoformat(),
                         processing_s=round(elapsed,3), first_audio_s=round(first,3) if first else None,
                         audio_duration_s=round(duration,3),audio_bytes=audio.stat().st_size if audio.exists() else 0,
                         inference_s=round(inference,3),first_audio_generation_s=round(max(0,first-prepared),3) if first else None,
                         rtf=round(inference/duration,3) if duration else None,
                         **getattr(engine,'memory_stats',lambda:{})())
        finally:
            with jobs_lock:
                cancel_flags.pop(identifier, None)


@app.post('/api/recordings', status_code=202)
def create_recording(request: GenerateRequest):
    spec=validate(request.model,request.language,request.speaker,request.instruct)
    if request.model!='base06' and model_path(store.MODEL_CACHE,request.model) is None:
        raise HTTPException(409,'Falta '+spec['label']+'. Ejecuta Instalar-Modelos-Qwen.cmd.')
    if spec['kind']=='base':
        if not request.voice_id:raise HTTPException(422,'Selecciona una voz para clonar.')
        voice = store.read_json(store.voice_path(request.voice_id))
        if voice['status'] != 'ready':raise HTTPException(409, 'Espera a que la voz esté preparada.')
    else:
        voice=dict(id=None,name=request.speaker,slug=store.slug(request.speaker))
    text = request.text.strip()
    if not text:
        raise HTTPException(422, 'Escribe el texto que quieres convertir en audio.')
    with jobs_lock:
        if len(cancel_flags) + len(design_jobs) >= 5:
            raise HTTPException(429, 'La cola está llena. Espera a que termine algún audio.')
        identifier = uuid.uuid4().hex
        timestamp = store.now()
        filename = f"{voice['slug']}_{timestamp:%Y-%m-%d_%H-%M-%S}_{identifier}"
        record = {'schema_version': 1, 'id': identifier, 'voice_id': voice['id'], 'voice_name': voice['name'],
                  'created_at': timestamp.isoformat(), 'text': text, 'characters': len(text), 'status': 'queued',
                  'filename': filename + '.mp3', 'metadata_filename': filename + '.json',
                  **request.model_dump(exclude={'text','voice_id'}),
                  'engine': spec['repo'].split('/')[-1], 'error': None, 'audio_bytes': 0,
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


class ComparisonRequest(GenerateRequest):
    pass


@app.post('/api/comparisons',status_code=202)
def create_comparison(request: ComparisonRequest):
    spec=validate(request.model,request.language,request.speaker,request.instruct)
    keys=('base06','base17') if spec['kind']=='base' else ('custom06','custom17')
    if request.instruct.strip():
        raise HTTPException(422,'Para una comparación equivalente, deja vacío el estilo: CustomVoice 0.6B no lo admite.')
    if not request.text.strip():raise HTTPException(422,'Escribe un texto para comparar.')
    if spec['kind']=='base':
        if not request.voice_id:raise HTTPException(422,'Selecciona una voz.')
        if store.read_json(store.voice_path(request.voice_id))['status']!='ready':raise HTTPException(409,'La voz no está preparada.')
    for key in keys:
        if model_path(store.MODEL_CACHE,key) is None:raise HTTPException(409,'Falta '+MODELS[key]['label']+'. Ejecuta Instalar-Modelos-Qwen.cmd.')
    with jobs_lock:
        if cancel_flags or design_jobs:raise HTTPException(409,'Espera a que terminen los trabajos actuales antes de comparar.')
        identifier=uuid.uuid4().hex
        recordings=[]
        for key in keys:
            for trial in (1,2):
                payload=request.model_dump()
                payload.update(model=key,force_reload=trial==1)
                record=create_recording(GenerateRequest(**payload))
                store.update(store.record_path(record['id']),comparison_id=identifier,trial=trial)
                recordings.append(record['id'])
        group=dict(schema_version=1,id=identifier,created_at=store.now().isoformat(),recordings=recordings,
                   models=list(keys),text=request.text,language=request.language,seed=request.seed,kind=spec['kind'])
        store.write_json(store.folder('comparisons')/(identifier+'.json'),group)
    return group


@app.get('/api/comparisons')
def list_comparisons():
    return sorted((store.read_json(p) for p in store.folder('comparisons').glob('*.json')),
                  key=lambda d:d['created_at'],reverse=True)[:50]


@app.get('/api/comparisons/{identifier}')
def get_comparison(identifier: str):
    group=store.read_json(store.folder('comparisons')/(store.valid_id(identifier)+'.json'))
    group['items']=[store.read_json(store.record_path(i)) for i in group['recordings']]
    return group


@app.get('/api/comparisons/{identifier}/json')
def comparison_json(identifier: str):
    return JSONResponse(get_comparison(identifier),headers={'Content-Disposition':f'attachment; filename="comparacion-{store.valid_id(identifier)}.json"'})


class EvaluationRequest(BaseModel):
    naturalness: int | None = Field(default=None,ge=1,le=5)
    intelligibility: int | None = Field(default=None,ge=1,le=5)
    similarity: int | None = Field(default=None,ge=1,le=5)
    notes: str = Field(default='',max_length=2000)


@app.post('/api/recordings/{identifier}/evaluation')
def evaluate_recording(identifier: str,request: EvaluationRequest):
    path=store.record_path(identifier)
    if store.read_json(path)['status']!='completed':raise HTTPException(409,'Escucha una grabación terminada antes de evaluarla.')
    return store.update(path,evaluation={**request.model_dump(),'updated_at':store.now().isoformat()})


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
