"""Install the optional public VoiceDesign model; never upload user data."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from voz_estudio import storage
os.environ['HF_HUB_OFFLINE']='0'
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
from huggingface_hub import snapshot_download

print('Descargando Qwen3-TTS 1.7B VoiceDesign…',flush=True)
snapshot_download('Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign',revision='5ecdb67327fd37bb2e042aab12ff7391903235d3',
                  cache_dir=str(storage.MODEL_CACHE/'hub'),token=False,
                  allow_patterns=['*.json','*.txt','*.safetensors','README.md','LICENSE'])
print('VoiceDesign preparado. Ya puedes crear voces desde la aplicación.',flush=True)
