"""Isolated GPU process: its memory is released when a preview finishes."""
import argparse
import json
import os
from pathlib import Path
import time
from .catalog import MODELS, model_path as catalog_model_path

DESIGN_MODEL = 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign'


def model_path(cache):
    return catalog_model_path(cache,'design17')


def generate(folder, cache):
    import numpy as np
    import soundfile as sf
    import torch
    from . import storage
    path=folder/'design.json'
    job=storage.read_json(path)
    key=job.get('model','design17')
    model_folder=catalog_model_path(cache,key)
    if model_folder is None:
        raise RuntimeError('Falta VoiceDesign 1.7B. Ejecuta Instalar-VoiceDesign.cmd.')
    torch.set_num_threads(4)
    cuda=torch.cuda.is_available() and os.environ.get('VOZ_DEVICE','auto')!='cpu'
    start=time.perf_counter()
    if cuda:
        from faster_qwen3_tts import FasterQwen3TTS
        model=FasterQwen3TTS.from_pretrained(str(model_folder),device='cuda',dtype=torch.bfloat16,
               attn_implementation='sdpa',local_files_only=True,max_seq_len=2048)
        model.warmup(prefill_len=300)
    else:
        from qwen_tts import Qwen3TTSModel
        model=Qwen3TTSModel.from_pretrained(str(model_folder),device_map='cpu',dtype=torch.float32,
               attn_implementation='sdpa',local_files_only=True)
    torch.manual_seed(job.get('seed',42));np.random.seed(job.get('seed',42))
    kwargs={k:job.get(k,default) for k,default in dict(language='Spanish',max_new_tokens=600,
                temperature=.9,top_k=50,top_p=1.,do_sample=True,repetition_penalty=1.05).items()}
    if MODELS[key]['kind']=='custom':
        wavs,sr=model.generate_custom_voice(text=job['text'],speaker=job['speaker'],
                    instruct=job['description'] or None,**kwargs)
    else:
        wavs,sr=model.generate_voice_design(text=job['text'],instruct=job['description'],**kwargs)
    audio=np.asarray(wavs[0],dtype=np.float32).reshape(-1)
    duration=len(audio)/sr
    if not 3<=duration<=35 or not np.isfinite(audio).all() or np.max(np.abs(audio))<.001:
        raise RuntimeError('La muestra no es válida o es demasiado larga. Prueba un texto de entre 10 y 20 segundos.')
    sf.write(folder/'preview.wav',audio,sr)
    storage.update(path,status='ready',duration_s=round(duration,3),sample_rate=sr,
                   processing_s=round(time.perf_counter()-start,3),device='cuda' if cuda else 'cpu',
                   model_revision=model_folder.name,error=None)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--folder',required=True)
    parser.add_argument('--cache',required=True)
    args=parser.parse_args()
    generate(Path(args.folder),Path(args.cache))
