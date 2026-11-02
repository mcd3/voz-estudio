"""Reassemble release parts and safely extract ZIP64 using bundled Python."""
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path


def extract(folder):
    folder=Path(folder).resolve()
    manifest=json.loads((folder/'release-manifest.json').read_text(encoding='utf-8-sig'))
    directory=manifest['directory']
    if Path(directory).name!=directory or directory in ('.','..'):
        raise ValueError('Nombre de carpeta no válido.')
    destination=folder/directory
    if destination.exists():
        raise RuntimeError('La carpeta ya existe. No se sobrescribirán sus datos. Usa una carpeta vacía.')
    combined=folder/(directory+'.zip')
    if combined.exists():
        raise RuntimeError('Ya existe el ZIP unido. Muévelo antes de repetir la preparación.')
    total=hashlib.sha256();size=0
    try:
        with combined.open('xb') as output:
            for item in manifest['parts']:
                name=item['name']
                if Path(name).name!=name or '/' in name or '\\' in name:
                    raise ValueError('Nombre de parte no válido.')
                path=folder/name
                if not path.is_file() or path.stat().st_size!=item['bytes']:
                    raise RuntimeError('Falta una parte o no está completa: '+name)
                h=hashlib.sha256()
                print('Comprobando y uniendo '+name,flush=True)
                with path.open('rb') as f:
                    for block in iter(lambda:f.read(4*1024*1024),b''):
                        h.update(block);total.update(block);size+=len(block);output.write(block)
                if h.hexdigest()!=item['sha256']:
                    raise RuntimeError('La huella de la parte no coincide: '+name)
        if total.hexdigest()!=manifest['archive_sha256'] or size!=manifest['archive_bytes']:
            raise RuntimeError('El archivo unido no coincide con el manifiesto.')
        with zipfile.ZipFile(combined) as archive:
            for entry in archive.infolist():
                name=entry.filename.replace('\\','/')
                if '..' in name.split('/') or not name.startswith(directory+'/') or ':' in name or name.startswith('/'):
                    raise RuntimeError('Ruta inesperada dentro del ZIP.')
                if (entry.external_attr>>16)&0o170000==0o120000:
                    raise RuntimeError('No se permiten enlaces simbólicos en el ZIP.')
            print('Extrayendo Voz Estudio. Puede tardar unos minutos…',flush=True)
            target=str(folder)
            if os.name=='nt' and not target.startswith('\\\\?\\'):
                target='\\\\?\\'+target
            archive.extractall(target)
    except Exception:
        # Only the newly created intermediate archive, never an existing ZIP.
        combined.unlink(missing_ok=True)
        raise
    combined.unlink()
    print('Preparado. Abre '+str(destination/'Iniciar.cmd'),flush=True)


if __name__=='__main__':
    extract(sys.argv[1] if len(sys.argv)>1 else Path(__file__).resolve().parent)
