import argparse
import hashlib
import importlib
import json
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from run import ROOT, configure


def check(args):
    configure()
    data=None
    if args.reference:
        data=Path(args.test_data).resolve() if args.test_data else None
        if data is None or data.is_relative_to(ROOT):
            raise RuntimeError('Usa --test-data con una carpeta privada fuera del paquete.')
        os.environ['VOZ_DATA_DIR']=str(data)
        os.environ['NUMBA_CACHE_DIR']=str(data/'cache'/'numba')
        os.environ['TORCH_HOME']=str(data/'cache'/'torch')
    outbound=[]
    def audit(event, arguments):
        if event == 'socket.connect':
            address=arguments[1]
            if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1'):
                outbound.append(str(address));raise RuntimeError('Conexión externa bloqueada en la prueba offline.')
        elif event == 'socket.getaddrinfo' and arguments[0] not in ('127.0.0.1','::1','localhost',None):
            outbound.append(str(arguments[0]));raise RuntimeError('Consulta externa bloqueada en la prueba offline.')
    sys.addaudithook(audit)
    if not Path(sys.executable).resolve().is_relative_to(ROOT/'runtime') or sys.version_info[:2] != (3,12):
        raise RuntimeError('La prueba debe ejecutarse con el Python incluido.')
    for path in sys.path:
        if path and not Path(path).resolve().is_relative_to(ROOT):
            raise RuntimeError('Ruta externa en sys.path: '+path)
    manifest=json.loads((ROOT/'bundle-manifest.json').read_text(encoding='utf-8'))
    entries=manifest['files'] if args.full else [e for e in manifest['files'] if e['path'] in ('runtime/python.exe','runtime/python312._pth','app/voz_estudio/app.py')]
    def verify_entry(entry):
        path=ROOT/entry['path']
        if not path.is_file() or path.stat().st_size!=entry['bytes']:
            raise RuntimeError('Archivo ausente o distinto: '+entry['path'])
        h=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(4*1024*1024),b''):
                h.update(block)
        if h.hexdigest()!=entry['sha256']:
            raise RuntimeError('Huella incorrecta: '+entry['path'])
    with ThreadPoolExecutor(max_workers=8) as pool:
        for index,_ in enumerate(pool.map(verify_entry,entries)):
            if args.full and index%2000==0:
                print(f'Integridad: {index}/{len(entries)}',flush=True)
    if args.libraries or args.reference:
        for name in ('torch','torchaudio','av','ctranslate2','faster_whisper','qwen_tts','faster_qwen3_tts','voz_estudio.app'):
            module=importlib.import_module(name)
            if not Path(module.__file__).resolve().is_relative_to(ROOT):
                raise RuntimeError('Biblioteca externa: '+name)
            print(name+': incluida',flush=True)
    if args.reference:
        # Keep personal material outside the release, including this test's data.
        from voz_estudio import storage, app as module
        storage.DATA=data
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError('La prueba NVIDIA necesita una GPU y su controlador.')
        from fastapi.testclient import TestClient
        with TestClient(module.app,base_url='http://localhost') as client:
            with Path(args.reference).open('rb') as f:
                response=client.post('/api/voices',data={'name':'Prueba portable'},files={'audio':('reference.wav',f,'audio/wav')})
            response.raise_for_status();identifier=response.json()['id']
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                voice=next(v for v in client.get('/api/voices').json() if v['id']==identifier)
                if voice['status']=='ready':break
                if voice['status']=='error':raise RuntimeError(voice['error'])
                time.sleep(.5)
            else:raise RuntimeError('El registro no terminó.')
            print('Registro y transcripción offline: correctos',flush=True)
            text='Hola. Esta grabación comprueba que Voz Estudio funciona con su propio Python, sus modelos y sus bibliotecas, sin descargar nada.'
            response=client.post('/api/recordings',json={'voice_id':identifier,'text':text})
            response.raise_for_status();record_id=response.json()['id']
            deadline=time.monotonic()+240
            while time.monotonic()<deadline:
                record=client.get('/api/recordings/'+record_id).json()
                if record['status']=='completed':break
                if record['status'] in ('error','cancelled'):raise RuntimeError(record['error'])
                time.sleep(.5)
            else:raise RuntimeError('La generación no terminó.')
            if record['device']!='cuda' or not record['audio_bytes'] or record['text']!=text:
                raise RuntimeError('No coincide la generación esperada.')
            import av,numpy as np
            path=storage.record_path(record_id).with_suffix('.mp3')
            with av.open(str(path)) as container:
                samples=np.concatenate([f.to_ndarray().reshape(-1) for f in container.decode(audio=0)])
            if not np.isfinite(samples).all() or np.max(np.abs(samples))<.001:
                raise RuntimeError('MP3 no válido.')
            metadata=client.get(f'/api/recordings/{record_id}/json').json()
            if metadata['text']!=text:raise RuntimeError('El JSON no conserva el texto.')
            print(json.dumps({k:record[k] for k in ('status','device','first_audio_s','processing_s','audio_duration_s')}) ,flush=True)
    if outbound:
        raise RuntimeError('Se detectaron intentos de acceso externo: '+str(outbound))
    print('Verificación correcta. Python y bibliotecas propios; cero conexiones externas.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--full',action='store_true')
    parser.add_argument('--libraries',action='store_true')
    parser.add_argument('--reference')
    parser.add_argument('--test-data')
    check(parser.parse_args())
