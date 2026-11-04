# Componentes de terceros

Voz Estudio contiene su interfaz y su gestión de datos. Instala como dependencias:

- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS): modelo Base 0.6B y tokenizador. Código/modelo bajo sus respectivas licencias Apache 2.0; consulta sus fichas antes de redistribuir pesos.
- [Faster Qwen3-TTS](https://github.com/andimarafioti/faster-qwen3-tts): MIT. Commit fijado `b35fdc7d71eb3e4d19e63f4b4a330a1aef31d682`, de Andres Marafioti. El patrón de inferencia sigue su API pública; se utiliza el paquete de compatibilidad qwen-tts-hf en un entorno independiente.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): MIT. Whisper small se utiliza para transcribir referencias en CPU.
- PyTorch, torchaudio, FastAPI, uvicorn, NumPy, SciPy, SoundFile y PyAV conservan sus propias licencias.
- [Qwen3-TTS 1.7B VoiceDesign](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign): modelo opcional para diseñar muestras de voz mediante descripciones, Apache 2.0. Revisión fijada `5ecdb67327fd37bb2e042aab12ff7391903235d3`. Después se usa el modelo Base 0.6B para clonar la muestra guardada.

Los modelos se descargan durante la instalación y no forman parte de este repositorio. Tampoco se distribuyen grabaciones, clones personales ni audios generados.

El instalador opcional de todos los modelos añade [Base 1.7B](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base), [CustomVoice 1.7B](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice) y [CustomVoice 0.6B](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice), con licencia Apache 2.0 según sus fichas. Sus repositorios y revisiones exactas están en `voz_estudio/catalog.py`. La instalación completa local conserva los pesos y las fichas; los pesos no se añaden al repositorio de código.
