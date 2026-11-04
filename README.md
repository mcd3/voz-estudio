# Voz Estudio 2.0

Una aplicación local para **registrar voces**, convertir textos en audio con la persona elegida y conservar una biblioteca de MP3 con su texto y metadatos JSON.

**Versión 2.0.0** · Cinco modelos Qwen3-TTS, diez idiomas y automático, creación de voces, clonación y comparación de resultados.

## Manual de uso

Abre **Manual de uso** desde la aplicación. Incluye una guía paso a paso para registrar y clonar voces, inventarlas con VoiceDesign, utilizar CustomVoice, elegir idiomas y comparar resultados. También puedes abrir el archivo `voz_estudio/static/manual.html` y utilizar Imprimir / guardar como PDF.

## Qué puedes hacer

- Registrar una voz con un nombre y una muestra WAV, MP3, M4A, FLAC u otro formato compatible con FFmpeg/PyAV.
- Preparar automáticamente una referencia de hasta unos 20 segundos y su transcripción, sin subir la grabación a servicios externos.
- Elegir entre Base 0.6B/1.7B, CustomVoice 0.6B/1.7B y VoiceDesign 1.7B, con idioma y ajustes de generación. Con NVIDIA se utiliza Faster Qwen3-TTS y CUDA Graphs.
- Crear muestras desde una descripción o una voz incluida y guardarlas como voces clonables.
- Comparar los tamaños 0.6B y 1.7B con el mismo texto y ajustes, separando carga, síntesis, primer audio y VRAM, y guardando valoraciones de escucha.
- Escuchar, descargar, buscar por persona o texto, reutilizar textos y cancelar generaciones.
- Guardar automáticamente **cada intento de generación**, incluido su texto completo, persona, fecha, estado y tiempos. Los audios parciales se conservan si una operación se cancela o falla.
- Descargar el JSON de un audio o exportar el historial completo.

Las instrucciones de interpretación se ofrecen en VoiceDesign y CustomVoice 1.7B. Una risa, un llanto o un acento concreto dependen del resultado del modelo y no están garantizados. No incluye un RAG ni un asistente conversacional.

## Requisitos

- Python **3.12 de 64 bits** y conexión a Internet para la instalación inicial.
- Windows 10/11 o un sistema compatible con las dependencias Python indicadas.
- Recomendado: GPU NVIDIA con controladores compatibles con PyTorch CUDA 12.8 y suficiente memoria libre. La configuración probada es una RTX 4090 Laptop de 16 GB.
- Sin CUDA se ofrece inferencia CPU, más lenta y con entrega de audio por pasajes. Linux y el modo CPU disponen de instalación, pero necesitan validarse en el hardware de destino. En macOS se utiliza CPU; no se ha implementado aceleración Metal.
- Varios GB libres para Python y los modelos. No se incluyen pesos de modelos en GitHub.

No se garantiza la misma latencia en cualquier ordenador. Al iniciar, la aplicación prepara el modelo y la aceleración en segundo plano. Puedes escribir mientras aparece «Preparando voz…»; el botón de generar se activa cuando el motor está listo. Las siguientes peticiones reutilizan el motor. Si la preparación falla, se muestra el error y se permite reintentar al generar. Las voces se interpretan a partir de referencias: no se entrena un modelo nuevo por persona.

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

### Modelos, idiomas y comparación

El instalador normal mantiene Base 0.6B como punto de partida. Ejecuta **Instalar-Modelos-Qwen.cmd** para instalar los cinco modelos públicos de la familia 12Hz. La copia completa local los incluye. Las revisiones están fijadas en `voz_estudio/catalog.py`; no se descargan pesos durante la generación.

| Modelo | Para qué sirve | Instrucciones de estilo |
|---|---|---|
| Base 0.6B | Clonar voces registradas y muestras guardadas | No |
| Base 1.7B | Clonar las mismas referencias con el modelo mayor | No |
| CustomVoice 0.6B | Generar con nueve voces incluidas | No |
| CustomVoice 1.7B | Nueve voces incluidas con instrucciones de interpretación | Sí |
| VoiceDesign 1.7B | Crear una muestra mediante una descripción | Sí |

En **Generar audio** elige Base para clonar una persona o CustomVoice para una voz incluida. En **Crear una voz** puedes usar VoiceDesign o cualquiera de los CustomVoice, escuchar la muestra y guardarla para clonarla después con cualquiera de los Base. Las voces incluidas son Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna y Sohee. Sus lenguas nativas se muestran en el selector; no hay una voz nativa española incluida.

Se puede elegir español, inglés, francés, alemán, italiano, portugués, chino, japonés, coreano, ruso o automático. El selector no traduce el texto. Español es el idioma, no una garantía de acento de España. En el registro de audio puedes elegir el idioma de la referencia o dejar que Whisper lo detecte. La lengua de la referencia y la del audio nuevo pueden ser diferentes.

Las opciones de generación incluyen semilla, temperatura, Top P, Top K, penalización de repetición, muestreo y límite de tokens de audio por pasaje. El límite puede cortar una generación si es insuficiente; textos largos se dividen en pasajes. La semilla permite repetir pruebas, pero no hace equivalentes dos modelos distintos ni garantiza igualdad entre equipos/versiones.

Para obtener otra variante de una voz diseñada con la misma descripción, cambia la semilla. Para reconstruir un portable con todos los modelos desde las herramientas locales, utiliza `python scripts/portable/build.py --all-models`; admite `--model-cache` y `--whisper-cache` para reutilizar los modelos instalados.

Para comparar, escribe el texto, selecciona el idioma y la voz o locutor, y pulsa **Comparar 0.6B y 1.7B con este texto**. La aplicación genera cuatro audios en cola: cada modelo con carga nueva y una repetición en memoria. Las comparaciones CustomVoice requieren dejar vacío el estilo para utilizar opciones comunes a ambos tamaños.

La pantalla **Comparar** separa carga, primer audio con/sin carga, síntesis, duración y pico de VRAM asignado por PyTorch. `RTF = tiempo de síntesis / duración del audio`; menor es más rápido y un valor menor de 1 significa que se sintetiza más deprisa de lo que se escucha. La VRAM medida no representa toda la memoria ocupada por el sistema u otros procesos. El tiempo de cola no se incluye en `processing_s`.

Tras escuchar las repeticiones, puntúa naturalidad, claridad y parecido/estabilidad, y escribe tus motivos. Las valoraciones se guardan en el JSON del audio. La aplicación muestra el modelo con menor RTF en esa prueba y compara tus puntuaciones cuando has evaluado ambos; no asigna una calidad automáticamente. Prueba varias frases, idiomas y referencias antes de elegir un modelo. Los audios, ajustes y comparaciones se guardan en `data`, y puedes descargar la comparación completa como JSON.

Una prueba local con RTX 4090 Laptop de 16 GB, un texto español de 121 caracteres, semilla 42 y ajustes comunes produjo estos valores con el modelo ya cargado:

| Modelo | Síntesis | Audio resultante | RTF | Pico VRAM PyTorch |
|---|---:|---:|---:|---:|
| Base 0.6B | 2,97 s | 7,76 s | 0,382 | 2787 MB |
| Base 1.7B | 4,22 s | 8,32 s | 0,507 | 4751 MB |
| CustomVoice 0.6B | 3,50 s | 9,20 s | 0,381 | 2433 MB |
| CustomVoice 1.7B | 5,11 s | 12,56 s | 0,407 | 4381 MB |

Son resultados de una frase y de dos casos de uso distintos: los Base compartían referencia y los CustomVoice compartían el locutor Ryan. Los 0.6B resultaron más rápidos en estas muestras y utilizaron menos VRAM; la calidad queda pendiente de escucha. Las pruebas de carga nueva miden recarga del modelo dentro de un servidor ya iniciado.

### Crear una voz con una descripción

La opción **Crear una voz** utiliza el modelo opcional **Qwen3-TTS 1.7B VoiceDesign**. Para instalarlo desde el repositorio, ejecuta `Instalar-VoiceDesign.cmd` después de la instalación normal. Descarga varios GB adicionales. La copia completa local ya tiene el modelo instalado.

1. Abre **Crear una voz**, ponle un nombre y describe el timbre, la edad aproximada, el acento y la forma de hablar. Por ejemplo: «Voz femenina adulta, cálida y serena, castellano de España, dicción clara y ritmo natural».
2. Escribe un texto de muestra de unos 10–20 segundos y pulsa **Crear muestra**. La descripción orienta el resultado; puedes probar distintas muestras.
3. Escucha el resultado. Si te gusta, pulsa **Guardar como voz clonable**. Aparecerá en **Mis voces** y **Generar audio**.
4. Selecciónala para leer nuevos textos con el motor Base 0.6B acelerado. La muestra y su texto se utilizan como referencia; no se entrena un modelo por personaje.

La GPU se utiliza de forma secuencial. Durante el diseño se libera el motor de clonación, se carga VoiceDesign en un proceso aislado y, al terminar, se prepara otra vez el motor de clonación. Cambiar de modelo añade una espera. También se admite CPU, con mayor latencia y sin una validación de rendimiento específica.

Los diseños y sus WAV se guardan en `data/designs`; las voces aceptadas se guardan en `data/voices` con su descripción y procedencia. Guardar dos veces la misma muestra conserva una sola voz. El modelo queda instalado para usarlo sin descargas posteriores. No se garantiza un acento o interpretación exactos por escribirlos en la descripción.

### Registrar voces y generar audio

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
