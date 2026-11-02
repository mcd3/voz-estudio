"""Build a relocatable Windows runtime from wheels, not from a copied venv.

Requires a Windows x64 Python 3.12 build host with pip. The result requires
neither Python, pip nor downloads on the destination machine.
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCK = json.loads((HERE / 'models.lock.json').read_text(encoding='utf-8'))


def say(message):
    print(message, flush=True)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inventory(bundle):
    paths=sorted(p for p in bundle.rglob('*') if p.is_file() and p!=bundle/'bundle-manifest.json')
    def entry(path):
        if path.is_symlink():
            raise RuntimeError('La distribución contiene un enlace.')
        return {'path':path.relative_to(bundle).as_posix(),'bytes':path.stat().st_size,'sha256':digest(path)}
    entries=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for index,item in enumerate(pool.map(entry,paths)):
            if index%2000==0:
                say(f'Inventario: {index}/{len(paths)} archivos')
            entries.append(item)
    return entries


def download(url, target, expected=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and (not expected or digest(target) == expected):
        return
    temporary = target.with_name(target.name + '.download')
    request = urllib.request.Request(url, headers={'User-Agent': 'Voz-Estudio-Portable/1.1'})
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as f:
        shutil.copyfileobj(response, f, 1024 * 1024)
    if expected and digest(temporary) != expected:
        raise RuntimeError('La huella no coincide: ' + target.name)
    temporary.replace(target)


def run(arguments):
    say('> ' + ' '.join(map(str, arguments[:5])) + (' …' if len(arguments) > 5 else ''))
    subprocess.run(list(map(str, arguments)), check=True, env={**os.environ, 'PIP_DISABLE_PIP_VERSION_CHECK':'1','PYTHONDONTWRITEBYTECODE':'1'})


def model_files(label, destination_cache, source_cache=None):
    definition = LOCK[label]
    repo, revision = definition['repo'], definition['revision']
    repository_dir = 'models--' + repo.replace('/', '--')
    destination = destination_cache / repository_dir / 'snapshots' / revision
    source = Path(source_cache) / repository_dir / 'snapshots' / revision if source_cache else None
    if source and source.exists():
        for path in sorted(source.rglob('*')):
            if path.is_file():
                target = destination / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)  # Dereference cache symlinks.
    else:
        request = urllib.request.Request(f'https://huggingface.co/api/models/{repo}/revision/{revision}')
        with urllib.request.urlopen(request, timeout=60) as response:
            siblings = json.load(response)['siblings']
        for entry in siblings:
            name = entry['rfilename']
            parts = Path(name).parts
            if '..' in parts or Path(name).is_absolute():
                raise RuntimeError('Ruta inesperada en el modelo.')
            allowed = (name.endswith(('.json','.txt','.safetensors')) if label == 'qwen'
                       else name in ('config.json','preprocessor_config.json','model.bin','tokenizer.json','vocabulary.json','vocabulary.txt'))
            if allowed:
                say('Modelo: ' + repo + '/' + name)
                download(f'https://huggingface.co/{repo}/resolve/{revision}/{urllib.parse.quote(name)}', destination / name)
    if not destination.exists() or not any(destination.rglob('*.safetensors' if label == 'qwen' else 'model.bin')):
        raise RuntimeError('El modelo está incompleto: ' + repo)
    refs = destination_cache / repository_dir / 'refs'
    refs.mkdir(parents=True, exist_ok=True)
    (refs / 'main').write_text(revision, encoding='ascii')


class SplitWriter(io.RawIOBase):
    def __init__(self, folder, name, limit=1500 * 1024 * 1024):
        self.folder, self.name, self.limit = Path(folder), name, limit
        self.position, self.handle, self.part_size = 0, None, 0
        self.archive_hash = hashlib.sha256()
        self.parts = []

    def writable(self):
        return True

    def seekable(self):
        return False

    def tell(self):
        return self.position

    def write(self, data):
        view = memoryview(data)
        written = len(view)
        while view:
            if self.handle is None or self.part_size == self.limit:
                if self.handle:
                    self.handle.close()
                path = self.folder / f'{self.name}.{len(self.parts)+1:03}'
                self.parts.append(path)
                self.handle = path.open('wb')
                self.part_size = 0
            count = min(len(view), self.limit - self.part_size)
            piece = view[:count]
            self.handle.write(piece)
            self.archive_hash.update(piece)
            self.position += count
            self.part_size += count
            view = view[count:]
        return written

    def finish(self):
        if self.handle:
            self.handle.close()
            self.handle = None
        return [{'name':p.name, 'bytes':p.stat().st_size, 'sha256':digest(p)} for p in self.parts]


def archive_bundle(bundle, release, python_zip):
    release.mkdir(parents=True, exist_ok=False)
    writer = SplitWriter(release, bundle.name + '.zip')
    with zipfile.ZipFile(writer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as archive:
        paths = sorted(p for p in bundle.rglob('*') if p.is_file())
        for index, path in enumerate(paths):
            if index % 1000 == 0:
                say(f'Comprimiendo: {index}/{len(paths)} archivos')
            if path.is_symlink():
                raise RuntimeError('No se permiten enlaces en la distribución.')
            archive.write(path, str(Path(bundle.name) / path.relative_to(bundle)))
    parts = writer.finish()
    manifest = {'schema_version':1, 'directory':bundle.name, 'archive_bytes':writer.position,
                'archive_sha256':writer.archive_hash.hexdigest(), 'parts':parts,
                'python_bootstrap':{'name':python_zip.name, 'sha256':digest(python_zip)}}
    (release / 'release-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    with zipfile.ZipFile(release / 'Preparar-Voz-Estudio.zip', 'w', compression=zipfile.ZIP_DEFLATED) as setup:
        setup.write(python_zip, python_zip.name)
        for name in ('Preparar.cmd','prepare.ps1','extract.py'):
            setup.write(HERE / name, name)
        setup.writestr('release-manifest.json', json.dumps(manifest, indent=2))
        setup.write(HERE / 'LEEME-PORTABLE.txt', 'LEEME-PORTABLE.txt')
    (release / 'SHA256SUMS.txt').write_text('\n'.join(digest(p)+'  '+p.name for p in sorted(release.iterdir()) if p.is_file())+'\n', encoding='ascii')
    say('Descarga preparada: ' + str(release))


def build(args):
    if sys.platform != 'win32' or sys.version_info[:2] != (3,12):
        raise RuntimeError('La construcción necesita Windows x64 y Python 3.12.')
    out = Path(args.output).resolve()
    version = (ROOT / 'voz_estudio' / '__init__.py').read_text().split("'")[1]
    bundle = out / ('VozEstudio-' + version + '-Windows-NVIDIA')
    if bundle.exists():
        raise RuntimeError('La carpeta de salida ya existe; utiliza otra para no sobrescribirla.')
    cache = ROOT / '.portable-cache'
    cache.mkdir(exist_ok=True)
    python_zip = cache / Path(urllib.parse.urlsplit(LOCK['python']['url']).path).name
    download(LOCK['python']['url'], python_zip, LOCK['python']['sha256'])
    lock_hash=digest(HERE/'requirements-windows.lock')[:12]
    wheels = cache / ('wheels-'+lock_hash)
    wheels.mkdir(exist_ok=True)
    requirements = (HERE / 'requirements-windows.lock').read_text().splitlines()
    cuda = [line for line in requirements if line.lower().startswith(('torch==','torchaudio=='))]
    other = [line for line in requirements if line and line not in cuda]
    say('1/6 · Preparando ruedas binarias y licencias')
    run([sys.executable,'-m','pip','wheel','--no-deps','--wheel-dir',wheels,'--index-url','https://download.pytorch.org/whl/cu128',*cuda])
    remaining = cache / 'requirements-other.txt'
    remaining.write_text('\n'.join(other)+'\n', encoding='utf-8')
    run([sys.executable,'-m','pip','wheel','--no-deps','--wheel-dir',wheels,'-r',remaining])
    say('2/6 · Creando Python independiente')
    runtime = bundle / 'runtime'
    runtime.mkdir(parents=True)
    with zipfile.ZipFile(python_zip) as archive:
        archive.extractall(runtime)
    (runtime / 'python312._pth').write_text('python312.zip\n.\nLib/site-packages\n../app\n..\nimport site\n',encoding='ascii')
    # A target install contains actual packages, not a virtual environment.
    wheel_files = sorted(wheels.glob('*.whl'))
    run([sys.executable,'-m','pip','install','--no-index','--no-deps','--no-compile','--target',runtime/'Lib'/'site-packages',*wheel_files])
    site=runtime/'Lib'/'site-packages'
    # Provenance is recorded by the lock; local wheel paths must not be shipped.
    for path in site.glob('*.dist-info/direct_url.json'):
        path.unlink()
    scripts=site/'bin'
    if scripts.exists():
        if scripts.resolve().parent!=site.resolve() or scripts.is_symlink():
            raise RuntimeError('Ruta inesperada de los ejecutables de instalación.')
        shutil.rmtree(scripts)
    if args.prune_wheels:
        # Only this build's dedicated cache, checked before recursive removal.
        resolved = wheels.resolve()
        if resolved.parent != cache.resolve() or not resolved.name.startswith('wheels-') or resolved.is_symlink():
            raise RuntimeError('Ruta inesperada de la caché de construcción.')
        shutil.rmtree(resolved)
    say('3/6 · Copiando solo el código de aplicación')
    app = bundle / 'app'
    shutil.copytree(ROOT/'voz_estudio', app/'voz_estudio', ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ('LICENSE','THIRD_PARTY.md'):
        shutil.copyfile(ROOT/name,bundle/name)
    for name in ('run.py','Iniciar.cmd','Detener.cmd','Comprobar.cmd','verify.py','LEEME-PORTABLE.txt'):
        shutil.copyfile(HERE/name,bundle/name)
    shutil.copyfile(HERE/'requirements-windows.lock',bundle/'requirements-windows.lock')
    shutil.copyfile(HERE/'models.lock.json',bundle/'models.lock.json')
    say('4/6 · Incluyendo modelos fijados, sin credenciales ni datos privados')
    model_files('qwen', bundle/'models'/'hf'/'hub', Path(args.model_cache)/'hub' if args.model_cache else None)
    model_files('whisper', bundle/'models'/'whisper', args.whisper_cache)
    licenses = bundle / 'licenses'
    licenses.mkdir()
    sources = {
        'Qwen3-TTS-LICENSE.txt':'https://raw.githubusercontent.com/QwenLM/Qwen3-TTS/main/LICENSE',
        'Whisper-LICENSE.txt':'https://raw.githubusercontent.com/openai/whisper/main/LICENSE',
        'Faster-Qwen3-TTS-LICENSE.txt':'https://raw.githubusercontent.com/andimarafioti/faster-qwen3-tts/b35fdc7d71eb3e4d19e63f4b4a330a1aef31d682/LICENSE',
        'Qwen-MODELCARD.md':f"https://huggingface.co/{LOCK['qwen']['repo']}/raw/{LOCK['qwen']['revision']}/README.md",
        'Whisper-MODELCARD.md':f"https://huggingface.co/{LOCK['whisper']['repo']}/raw/{LOCK['whisper']['revision']}/README.md",
    }
    for name,url in sources.items():
        download(url,licenses/name)
    say('5/6 · Inventario de integridad y prueba de bibliotecas')
    entries=inventory(bundle)
    manifest={'schema_version':1,'version':version,'platform':'windows-amd64-cu128','python':LOCK['python']['version'],
              'models':{k:LOCK[k] for k in ('qwen','whisper')},'files':entries}
    (bundle/'bundle-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    run([runtime/'python.exe','-B',bundle/'verify.py','--libraries'])
    say('6/6 · Paquete independiente listo: ' + str(bundle))
    if not args.no_archive:
        archive_bundle(bundle,out/'release',python_zip)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(ROOT/'portable-dist'))
    parser.add_argument('--model-cache')
    parser.add_argument('--whisper-cache')
    parser.add_argument('--no-archive',action='store_true')
    parser.add_argument('--prune-wheels',action='store_true')
    build(parser.parse_args())
