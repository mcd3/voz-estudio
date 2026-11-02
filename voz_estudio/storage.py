"""Private local files, atomic JSON updates and portable relative paths."""
import json
import os
import re
import tempfile
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('VOZ_DATA_DIR', ROOT / 'data')).resolve()
MODEL_CACHE = Path(os.environ.get('VOZ_MODEL_CACHE', ROOT / 'models' / 'hf')).resolve()
WHISPER_CACHE = Path(os.environ.get('VOZ_WHISPER_CACHE', ROOT / 'models' / 'whisper')).resolve()
LOCK = threading.RLock()


def now():
    return datetime.now(ZoneInfo(os.environ.get('VOZ_TIMEZONE', 'Europe/Madrid')))


def slug(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')[:60] or 'voz'


def valid_id(value):
    if not re.fullmatch(r'[a-f0-9]{32}', value):
        raise ValueError('Identificador no válido.')
    return value


def folder(kind):
    path = DATA / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def voice_path(identifier):
    return folder('voices') / valid_id(identifier) / 'voice.json'


def record_path(identifier):
    valid_id(identifier)
    matches = list(folder('recordings').glob(f'*_{identifier}.json'))
    if len(matches) != 1:
        raise FileNotFoundError('Audio no encontrado.')
    return matches[0]


def write_json(path, value):
    with LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            # Windows indexers/antivirus and external readers can temporarily
            # deny replacement even when the application's own lock is held.
            for attempt in range(9):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if attempt == 8:
                        raise
                    time.sleep(min(0.02 * 2 ** attempt, 0.4))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def read_json(path):
    with LOCK:
        return json.loads(path.read_text(encoding='utf-8'))


def update(path, **fields):
    with LOCK:
        data = read_json(path)
        data.update(fields)
        write_json(path, data)
        return data


def voices():
    with LOCK:
        return sorted((read_json(p) for p in folder('voices').glob('*/voice.json')),
                      key=lambda v: v['name'].casefold())


def records():
    with LOCK:
        return sorted((read_json(p) for p in folder('recordings').glob('*.json')),
                      key=lambda r: r['created_at'], reverse=True)


def recover_interrupted():
    for voice in voices():
        if voice['status'] in ('queued', 'processing'):
            update(voice_path(voice['id']), status='error', error='El registro se interrumpió. Puedes reintentarlo.')
    for record in records():
        if record['status'] in ('queued', 'loading', 'generating'):
            update(record_path(record['id']), status='error', error='La generación se interrumpió al cerrar la aplicación.')
