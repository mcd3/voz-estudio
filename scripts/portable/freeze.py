"""Record the tested Windows runtime without absolute paths or editable installs."""
from importlib.metadata import distributions
from pathlib import Path

root = Path(__file__).resolve().parent
items = []
for distribution in distributions():
    name, version = distribution.metadata['Name'], distribution.version
    normalized = name.lower().replace('_', '-')
    if normalized in ('pip', 'voz-estudio'):
        continue
    if normalized == 'faster-qwen3-tts':
        items.append('faster-qwen3-tts @ https://github.com/andimarafioti/faster-qwen3-tts/archive/b35fdc7d71eb3e4d19e63f4b4a330a1aef31d682.zip')
    else:
        items.append(f'{name}=={version}')
(root / 'requirements-windows.lock').write_text('\n'.join(sorted(items, key=str.casefold)) + '\n', encoding='utf-8')
print(f'{len(items)} dependencias fijadas para el paquete Windows.')
