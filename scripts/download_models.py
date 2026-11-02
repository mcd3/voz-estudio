"""Download public model weights; never uploads references or user data."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voz_estudio import storage

os.environ['HF_HOME'] = str(storage.MODEL_CACHE)
from huggingface_hub import snapshot_download
from faster_whisper.utils import download_model

print('Descargando Qwen3-TTS 0.6B y su tokenizador…', flush=True)
snapshot_download('Qwen/Qwen3-TTS-12Hz-0.6B-Base', cache_dir=str(storage.MODEL_CACHE / 'hub'),
                  token=False, ignore_patterns=['*.md', '*.gitattributes'])
print('Descargando Whisper small para registrar voces en local…', flush=True)
download_model('small', cache_dir=str(storage.WHISPER_CACHE), use_auth_token=False)
print('Modelos preparados. Ya puedes iniciar Voz Estudio.', flush=True)
