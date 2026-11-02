"""Portable launcher: all paths derive from this file, never from the build PC."""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def configure(root=ROOT):
    os.environ.pop('PYTHONHOME', None)
    os.environ.pop('PYTHONPATH', None)
    paths = {'VOZ_DATA_DIR':root/'data', 'VOZ_MODEL_CACHE':root/'models'/'hf',
             'VOZ_WHISPER_CACHE':root/'models'/'whisper', 'HF_HOME':root/'models'/'hf',
             'HF_HUB_CACHE':root/'models'/'hf'/'hub', 'HUGGINGFACE_HUB_CACHE':root/'models'/'hf'/'hub',
             'TORCH_HOME':root/'data'/'cache'/'torch', 'NUMBA_CACHE_DIR':root/'data'/'cache'/'numba'}
    for key,value in paths.items():
        os.environ[key] = str(value)
    for key in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','HF_DATASETS_OFFLINE',
                'HF_HUB_DISABLE_TELEMETRY','HF_HUB_DISABLE_IMPLICIT_TOKEN','DO_NOT_TRACK','PYTHONDONTWRITEBYTECODE'):
        os.environ[key] = '1'
    os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    os.environ['PYTHONUTF8'] = '1'
    sys.dont_write_bytecode = True


def status(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status', timeout=1) as response:
        return json.load(response)


def start(port, no_browser):
    configure()
    url = f'http://127.0.0.1:{port}'
    try:
        existing = status(port)
    except Exception:
        existing = None
    saved = ROOT / 'data' / 'server-portable.json'
    if existing:
        if not saved.exists() or existing.get('instance') != json.loads(saved.read_text())['instance']:
            raise RuntimeError('El puerto está ocupado por otra aplicación. Usa Iniciar.cmd --port 3021.')
    else:
        logs = ROOT / 'data' / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        instance = uuid.uuid4().hex
        arguments = [sys.executable, '-B', '-m', 'voz_estudio', '--port', str(port), '--instance', instance]
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        with (logs/'server.log').open('ab') as output, (logs/'server-error.log').open('ab') as error:
            subprocess.Popen(arguments, cwd=ROOT, stdout=output, stderr=error, creationflags=flags, env=os.environ.copy())
        print('Iniciando Voz Estudio portable…', flush=True)
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            try:
                existing=status(port)
                if existing.get('instance') == instance:
                    break
                raise RuntimeError('El puerto pertenece a otro proceso.')
            except (OSError,TimeoutError):
                time.sleep(.5)
        else:
            raise RuntimeError('El servidor no ha iniciado. Revisa data/logs/server-error.log.')
        saved.write_text(json.dumps({'pid':existing['pid'],'instance':instance,'port':port}),encoding='utf-8')
    print('Voz Estudio portable: '+url, flush=True)
    if not no_browser:
        webbrowser.open(url)


def stop():
    configure()
    saved=ROOT/'data'/'server-portable.json'
    if not saved.exists():
        print('No hay un servidor portable registrado.');return
    info=json.loads(saved.read_text())
    try:
        current=status(info['port'])
    except Exception:
        print('El servidor ya está detenido.');return
    if current.get('instance') != info['instance'] or current.get('pid') != info['pid']:
        raise RuntimeError('El proceso no coincide con esta copia portable. No se ha detenido.')
    # psutil is bundled; verify process arguments as well as the live instance.
    import psutil
    process=psutil.Process(info['pid'])
    command=process.cmdline()
    if 'voz_estudio' not in command or info['instance'] not in command:
        raise RuntimeError('El proceso no pertenece a esta aplicación.')
    process.terminate()
    print('Voz Estudio portable detenido. Los datos se conservan en data.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['start','stop'])
    parser.add_argument('--port',type=int,default=3020)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    try:
        start(args.port,args.no_browser) if args.action=='start' else stop()
    except Exception as exc:
        print('Error: '+str(exc),file=sys.stderr);sys.exit(1)
