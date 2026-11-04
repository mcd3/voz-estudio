"""Optional Qwen model installer. Downloads public weights, never user audio."""
import argparse
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from voz_estudio.catalog import MODELS,model_path
from voz_estudio import storage
os.environ['HF_HUB_OFFLINE']='0'
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
from huggingface_hub import snapshot_download
parser=argparse.ArgumentParser()
parser.add_argument('--model',choices=['all',*MODELS],default='all')
args=parser.parse_args()
for key,model in MODELS.items():
    if args.model not in ('all',key):continue
    existing=model_path(storage.MODEL_CACHE,key)
    if existing and existing.name==model['revision'] and (existing/'speech_tokenizer'/'model.safetensors').is_file():
        print(model['label']+': ya instalado.',flush=True);continue
    target=storage.MODEL_CACHE/'hub'/('models--'+model['repo'].replace('/','--'))/'snapshots'/model['revision']
    print('Descargando '+model['repo'],flush=True)
    snapshot_download(model['repo'],revision=model['revision'],local_dir=str(target),token=False,
                      allow_patterns=['*.json','*.txt','*.safetensors','README.md','LICENSE'])
print('Modelos preparados.',flush=True)
