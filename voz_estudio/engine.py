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
        speech, _ = model.transcribe(resample_poly(audio, 2, 3), language='es', beam_size=5, vad_filter=True)
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
            partial, _ = model.transcribe(resample_poly(audio[int(start * 24000):int(end * 24000)], 2, 3), language='es')
            text = ' '.join(s.text.strip() for s in partial)
        reference = audio[int(start * 24000):int(end * 24000)]
        if len(reference) < 3 * 24000 or not text:
            raise ValueError('La muestra no contiene suficiente habla. Graba entre 10 y 30 segundos.')
        sf.write(folder / 'reference.wav', reference, 24000)
        (folder / 'reference.txt').write_text(text, encoding='utf-8')
        store.update(path, status='ready', transcript=text, duration_s=round(len(reference) / 24000, 3),
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

    def load(self):
        if self.model is not None:
            return
        self.state = 'loading'
        try:
            import torch
            torch.set_num_threads(4)
            snapshots = store.MODEL_CACHE / 'hub' / 'models--Qwen--Qwen3-TTS-12Hz-0.6B-Base' / 'snapshots'
            if not snapshots.exists():
                raise RuntimeError('Falta el modelo. Ejecuta el instalador o scripts/download_models.py.')
            paths = sorted(snapshots.iterdir())
            model_path = next((p for p in paths if (p / 'model.safetensors').exists()), None)
            if model_path is None:
                raise RuntimeError('La descarga del modelo está incompleta. Ejecuta el instalador.')
            cuda = torch.cuda.is_available() and os.environ.get('VOZ_DEVICE', 'auto') != 'cpu'
            if cuda:
                from faster_qwen3_tts import FasterQwen3TTS
                self.model = FasterQwen3TTS.from_pretrained(str(model_path), device='cuda', dtype=torch.bfloat16,
                                   attn_implementation='sdpa', local_files_only=True, max_seq_len=2048)
                self.model.warmup(prefill_len=300)
                self.mode = 'cuda'
            else:
                from qwen_tts import Qwen3TTSModel
                self.model = Qwen3TTSModel.from_pretrained(str(model_path), device_map='cpu', dtype=torch.float32,
                                         attn_implementation='sdpa', local_files_only=True)
                self.mode = 'cpu'
            self.state, self.error = 'ready', None
        except Exception as exc:
            self.model = None
            self.state, self.error = 'error', str(exc)
            raise

    def generate(self, text, voice):
        self.load()
        folder = store.voice_path(voice['id']).parent
        reference, transcript = str(folder / 'reference.wav'), voice['transcript']
        for passage in passages(text):
            if self.mode == 'cuda':
                yield from self.model.generate_voice_clone_streaming(
                    text=passage, language='Spanish', ref_audio=reference, ref_text=transcript,
                    append_silence=False, chunk_size=8, max_new_tokens=1200)
            else:
                wavs, sr = self.model.generate_voice_clone(text=passage, language='Spanish', ref_audio=reference,
                                                        ref_text=transcript, max_new_tokens=1200)
                yield wavs[0], sr, {}
