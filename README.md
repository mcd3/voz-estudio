# Voz Estudio

Una aplicación local para **registrar voces**, convertir textos en audio con la persona elegida y conservar una biblioteca de MP3 con su texto y metadatos JSON.

## Qué puedes hacer

- Registrar una voz con un nombre y una muestra WAV, MP3, M4A, FLAC u otro formato compatible con FFmpeg/PyAV.
- Preparar automáticamente una referencia de hasta unos 20 segundos y su transcripción, sin subir la grabación a servicios externos.
- Generar textos en castellano con Qwen3-TTS Base 0.6B. Con NVIDIA se utiliza Faster Qwen3-TTS y CUDA Graphs, con audio progresivo.
- Escuchar, descargar, buscar por persona o texto, reutilizar textos y cancelar generaciones.
- Guardar automáticamente **cada intento de generación**, incluido su texto completo, persona, fecha, estado y tiempos. Los audios parciales se conservan si una operación se cancela o falla.
- Descargar el JSON de un audio o exportar el historial completo.

La aplicación usa voz natural. La prueba de control de risas y llanto no funcionó y no se ofrece esa función. No incluye un RAG ni un asistente conversacional.

## Requisitos

- Python **3.12 de 64 bits** y conexión a Internet para la instalación inicial.
- Windows 10/11 o un sistema compatible con las dependencias Python indicadas.
- Recomendado: GPU NVIDIA con controladores compatibles con PyTorch CUDA 12.8 y suficiente memoria libre. La configuración probada es una RTX 4090 Laptop de 16 GB.
- Sin CUDA se ofrece inferencia CPU, más lenta y con entrega de audio por pasajes. Linux y el modo CPU disponen de instalación, pero necesitan validarse en el hardware de destino. En macOS se utiliza CPU; no se ha implementado aceleración Metal.
- Varios GB libres para Python y los modelos. No se incluyen pesos de modelos en GitHub.

No se garantiza la misma latencia en cualquier ordenador. La carga inicial prepara el modelo y la aceleración; las siguientes peticiones reutilizan el motor. Las voces se interpretan a partir de referencias: no se entrena un modelo nuevo por persona.

## Instalación en Windows

1. Instala [Python 3.12 de 64 bits](https://www.python.org/downloads/).
2. Descarga este repositorio como ZIP y extráelo en una carpeta, o clónalo.
3. Abre **`Instalar.cmd`**. Creará `.venv`, instalará PyTorch y las dependencias, y descargará Qwen3-TTS y Whisper small. Solo necesita Internet para instalar y descargar los modelos.
4. Abre **`Iniciar.cmd`**. Se abrirá [Voz Estudio](http://127.0.0.1:3010).
5. Para cerrar el servidor utiliza **`Detener.cmd`**. Cerrar la pestaña no detiene el proceso.

Para forzar CPU: `Instalar.cmd -CPU`. Para elegir otro puerto: `Iniciar.cmd -Port 3011`.

También puedes arrancar en consola, donde Ctrl+C detiene la aplicación:

```powershell
.\.venv\Scripts\python.exe -m voz_estudio
```

## Linux

```bash
bash install.sh
bash start.sh
```

Necesitas `python3.12` y su módulo `venv`. Para forzar CPU: `VOZ_DEVICE=cpu bash install.sh`, y después `VOZ_DEVICE=cpu bash start.sh`.

## Uso

1. En **Mis voces**, escribe el nombre de la persona y selecciona su audio. Recomendamos 10–30 segundos de voz clara, sin música ni otras personas. Se aceptan de 3 segundos a 2 minutos y hasta 50 MB.
2. Espera a **Preparada**. Se crea una referencia y se transcribe localmente. Si el registro falla, el mensaje explica el problema y permite reintentarlo.
3. En **Generar audio**, selecciona la persona, escribe el texto y pulsa **Generar audio**. Puedes escuchar mientras se genera si tu navegador admite MP3 con MediaSource.
4. En **Biblioteca** encontrarás el audio, el texto completo, la fecha y los tiempos. Puedes descargar el MP3 y su JSON, buscar o reutilizar el texto.

Las generaciones se procesan de una en una, con una cola limitada. Si cierras la pestaña, el servidor continúa guardando el audio. Si detienes el servidor, al volver a arrancar los trabajos incompletos aparecen como interrumpidos; los textos se conservan.

## Dónde se guarda todo

```text
data/
  voices/
    <id>/
      voice.json            # Nombre, estado, transcripción y fechas
      original.audio        # Archivo original, formato detectado por su contenido
      reference.wav         # Referencia mono a 24 kHz
      reference.txt         # Texto de esa referencia
  recordings/
    persona_2026-11-02_12-30-00_<id>.mp3
    persona_2026-11-02_12-30-00_<id>.json
  logs/
```

El nombre combina persona, fecha/hora y un identificador único para evitar sobrescrituras. Las fechas incluyen zona horaria; por defecto se utiliza Europe/Madrid.

El JSON de una grabación incluye `voice_id`, `voice_name`, `created_at`, `text`, `status`, `audio_duration_s`, `first_audio_s`, `processing_s`, `device`, `filename` y posibles errores. Los tiempos incluyen la preparación necesaria para esa petición y no incluyen la espera previa en cola.

**Copia de seguridad o traslado:** detén el servidor y copia la carpeta `data` completa. El exportador JSON contiene el historial y los textos, pero no sustituye una copia de los audios. En otro equipo instala primero la aplicación, copia `data` y arranca. Los modelos se pueden descargar de nuevo.

## Configuración

Los valores predeterminados funcionan sin cambios. En Windows puedes copiar `settings.example.json` a `settings.local.json` para usar otras rutas. El lanzador aplica esas variables al proceso. En Linux utiliza variables de entorno.

| Variable | Uso |
|---|---|
| `VOZ_DATA_DIR` | Carpeta privada de voces y grabaciones. Por defecto `data` en el proyecto. |
| `VOZ_MODEL_CACHE` | Caché Hugging Face para Qwen3-TTS. Por defecto `models/hf`. |
| `VOZ_WHISPER_CACHE` | Caché Whisper. Por defecto `models/whisper`. |
| `VOZ_DEVICE` | `auto` o `cpu`. |
| `VOZ_TIMEZONE` | Por defecto `Europe/Madrid`. |

Para reutilizar modelos ya descargados, el instalador Windows admite `-ModelCache RUTA -WhisperCache RUTA`. La aplicación no depende del proyecto VibeVoice ni de una ruta de un ordenador concreto.

## API local

- `POST /api/voices`: formulario multipart con `name` y `audio`; responde 202 mientras prepara la voz.
- `GET /api/voices`: voces y estado de registro.
- `POST /api/recordings`: JSON `{"voice_id":"<id>","text":"Hola"}`; responde 202 con un trabajo persistido.
- `GET /api/recordings/{id}`: estado, texto y métricas.
- `GET /api/recordings/{id}/stream`: MP3 progresivo mientras se genera.
- `GET /api/recordings/{id}/audio`: audio terminado o parcial finalizado; `?download=true` fuerza descarga.
- `GET /api/recordings/{id}/json`: metadatos y texto.
- `GET /api/recordings?q=texto&voice_id=<id>&offset=0&limit=50`: historial paginado.
- `POST /api/recordings/{id}/cancel`: solicita detener el siguiente fragmento.
- `GET /api/export`: exportación completa en JSON.

La interfaz de documentación interactiva está en `/docs`. El servidor escucha solo en 127.0.0.1: no tiene autenticación ni está diseñado para publicarse directamente en Internet.

## Código público, datos privados

`.gitignore` excluye `data`, `models`, `.venv`, registros y configuración local. **Las voces, grabaciones y textos personales no se suben a GitHub**. Los ejemplos de este README son ficticios. Revisa los archivos antes de crear tus propios commits.

Licencia del código de Voz Estudio: MIT. Consulta [THIRD_PARTY.md](THIRD_PARTY.md) para las dependencias y licencias de modelos.

## Comprobaciones

```bash
python -m unittest discover -s tests -v
node --check voz_estudio/static/app.js
```

Las pruebas de API verifican selección de persona, persistencia de texto y JSON, MP3, nombres únicos, cancelación, errores y recuperación. Utilizan un motor simulado para no descargar pesos ni necesitar GPU en CI. La calidad y latencia real requieren pruebas en el equipo de destino.
