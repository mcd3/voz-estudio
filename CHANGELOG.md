# Historial de cambios

## 2.0.0 · 4 de noviembre de 2026

- Cinco modelos: Base 0.6B/1.7B, CustomVoice 0.6B/1.7B y VoiceDesign 1.7B.
- Selección de diez idiomas y automático, con idioma independiente para las referencias.
- Creación de muestras, escucha previa y guardado idempotente como voz clonable.
- Elección explícita entre voces propias, voces inventadas y voces predefinidas.
- Instrucciones de estilo habilitadas según las capacidades de cada modelo.
- Semilla y parámetros de muestreo guardados en los JSON de generación.
- Comparaciones con carga nueva y repetición, métricas separadas y valoraciones de escucha.
- Manual de uso integrado, imprimible y disponible sin servicios externos.
- Texto de muestra de hasta 390 caracteres.
- Instaladores opcionales con revisiones de modelos fijadas; pesos y datos personales excluidos de Git.
- Preparación del motor al arrancar y cierre de los procesos de creación de voces.

Los datos existentes se conservan. La instalación normal mantiene Base 0.6B como punto de partida; Instalar-Modelos-Qwen.cmd instala los modelos adicionales.
