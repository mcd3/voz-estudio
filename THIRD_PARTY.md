# Componentes de terceros

Voz Estudio contiene su interfaz y su gestión de datos. Instala como dependencias:

- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS): modelo Base 0.6B y tokenizador. Código/modelo bajo sus respectivas licencias Apache 2.0; consulta sus fichas antes de redistribuir pesos.
- [Faster Qwen3-TTS](https://github.com/andimarafioti/faster-qwen3-tts): MIT. Commit fijado `b35fdc7d71eb3e4d19e63f4b4a330a1aef31d682`, de Andres Marafioti. El patrón de inferencia sigue su API pública; se utiliza el paquete de compatibilidad qwen-tts-hf en un entorno independiente.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): MIT. Whisper small se utiliza para transcribir referencias en CPU.
- PyTorch, torchaudio, FastAPI, uvicorn, NumPy, SciPy, SoundFile y PyAV conservan sus propias licencias.

Los modelos se descargan durante la instalación y no forman parte de este repositorio. Tampoco se distribuyen grabaciones, clones personales ni audios generados.
