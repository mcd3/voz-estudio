"""Lazy local models. CPU ASR and serialized voice synthesis."""
import os
import re
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from . import storage as store
from .audio import load_audio
from .catalog import MODELS, LANGUAGE_CODES, model_path

os.environ.setdefault('HF_HOME', str(store.MODEL_CACHE))
os.environ.setdefault('HF_HUB_DISABLE_IMPLICIT_TOKEN', '1')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')


def prepare_voice(identifier):
    path = store.voice_path(identifier)
    store.update(path, status='processing', error=None)
    try:
        voice = store.read_json(path)
        folder = path.parent
        audio = load_audio(folder / 'original.audio')
        from faster_whisper import WhisperModel
        model = WhisperModel('small', device='cpu', compute_type='int8', cpu_threads=4,
                            download_root=str(store.WHISPER_CACHE), local_files_only=True, use_auth_token=False)
        reference_language=LANGUAGE_CODES[voice.get('language','Spanish')]
        speech, info = model.transcribe(resample_poly(audio, 2, 3), language=reference_language, beam_size=5, vad_filter=True)
        speech = list(speech)
        if not speech:
            raise ValueError('No se ha reconocido habla. Prueba una muestra más clara.')
        start = max(0, speech[0].start - 0.1)
        chosen = [s for s in speech if s.end - start <= 20]
        if chosen:
            end = min(len(audio) / 24000, chosen[-1].end + 0.1)
            text = ' '.join(s.text.strip() for s in chosen)
        else:
            end = min(start + 18, len(audio) / 24000)
            partial, _ = model.transcribe(resample_poly(audio[int(start * 24000):int(end * 24000)], 2, 3), language=reference_language)
            text = ' '.join(s.text.strip() for s in partial)
        reference = audio[int(start * 24000):int(end * 24000)]
        if len(reference) < 3 * 24000 or not text:
            raise ValueError('La muestra no contiene suficiente habla. Graba entre 10 y 30 segundos.')
        sf.write(folder / 'reference.wav', reference, 24000)
        (folder / 'reference.txt').write_text(text, encoding='utf-8')
        store.update(path, status='ready', transcript=text, transcription_language=info.language, duration_s=round(len(reference) / 24000, 3),
                     original_duration_s=round(len(audio) / 24000, 3), ready_at=store.now().isoformat(), error=None)
    except Exception as exc:
        store.update(path, status='error', error=str(exc))


def passages(text):
    piece = ''
    for word in re.findall(r'\S+', text):
        if piece and len(piece) + len(word) > 230:
            yield piece
            piece = ''
        piece = (piece + ' ' + word).strip()
    if piece:
        yield piece


class Engine:
    def __init__(self):
        self.model = None
        self.mode = None
        self.state = 'idle'
        self.error = None
        self.model_key = None
        self.revision = None

    def unload(self):
        import gc
        self.model = None
        self.model_key = None
        self.revision = None
        self.mode, self.state, self.error = None, 'idle', None
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def load(self, key='base06'):
        if self.model is not None and self.model_key==key:
            return False
        if self.model is not None:self.unload()
        self.state = 'loading'
        try:
            import torch
            if torch.cuda.is_available():torch.cuda.reset_peak_memory_stats()
            torch.set_num_threads(4)
            folder = model_path(store.MODEL_CACHE,key)
            if folder is None:
                raise RuntimeError('Falta '+MODELS[key]['label']+'. Ejecuta Instalar-Modelos-Qwen.cmd.')
            cuda = torch.cuda.is_available() and os.environ.get('VOZ_DEVICE', 'auto') != 'cpu'
            if cuda:
                from faster_qwen3_tts import FasterQwen3TTS
                self.model = FasterQwen3TTS.from_pretrained(str(folder), device='cuda', dtype=torch.bfloat16,
                                   attn_implementation='sdpa', local_files_only=True, max_seq_len=2048)
                self.model.warmup(prefill_len=300)
                self.mode = 'cuda'
            else:
                from qwen_tts import Qwen3TTSModel
                self.model = Qwen3TTSModel.from_pretrained(str(folder), device_map='cpu', dtype=torch.float32,
                                         attn_implementation='sdpa', local_files_only=True)
                self.mode = 'cpu'
            self.state, self.error = 'ready', None
            self.model_key, self.revision = key, folder.name
            return True
        except Exception as exc:
            self.model = None
            self.state, self.error = 'error', str(exc)
            raise

    def memory_stats(self, reset=False):
        import torch
        if not torch.cuda.is_available():return {}
        if reset:torch.cuda.reset_peak_memory_stats()
        return {'peak_vram_mb':round(torch.cuda.max_memory_allocated()/1024**2,1)} if self.mode=='cuda' else {}

    def generate(self, text, voice, options=None):
        options=options or {}
        key=options.get('model','base06')
        self.load(key)
        import torch
        seed=options.get('seed',42)
        torch.manual_seed(seed);np.random.seed(seed)
        kwargs={k:options.get(k,default) for k,default in dict(temperature=.9,top_p=1.,top_k=50,
                    do_sample=True,repetition_penalty=1.05,max_new_tokens=1200).items()}
        kwargs['language']=options.get('language','Spanish')
        if MODELS[key]['kind']=='base':
            folder = store.voice_path(voice['id']).parent
            kwargs.update(ref_audio=str(folder/'reference.wav'),ref_text=voice['transcript'])
            method='generate_voice_clone'
        else:
            kwargs.update(speaker=options['speaker'],instruct=options.get('instruct') or None)
            method='generate_custom_voice'
        for passage in passages(text):
            if self.mode == 'cuda':
                streaming=dict(kwargs,chunk_size=8)
                if MODELS[key]['kind']=='base':streaming['append_silence']=False
                yield from getattr(self.model,method+'_streaming')(text=passage,**streaming)
            else:
                wavs, sr = getattr(self.model,method)(text=passage,**kwargs)
                yield wavs[0], sr, {}
