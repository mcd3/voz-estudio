import io

import av
import numpy as np


def load_audio(path, limit_seconds=120):
    frames = []
    count = 0
    with av.open(str(path)) as container:
        if not container.streams.audio:
            raise ValueError('El archivo no contiene audio.')
        resampler = av.AudioResampler(format='fltp', layout='mono', rate=24000)
        for frame in container.decode(audio=0):
            for output in resampler.resample(frame):
                samples = output.to_ndarray().reshape(-1)
                count += len(samples)
                if count > limit_seconds * 24000:
                    raise ValueError(f'La muestra debe durar como máximo {limit_seconds} segundos.')
                frames.append(samples)
        for output in resampler.resample(None):
            frames.append(output.to_ndarray().reshape(-1))
    if not frames:
        raise ValueError('No se ha podido leer audio del archivo.')
    audio = np.concatenate(frames).astype(np.float32)
    if not np.isfinite(audio).all() or len(audio) < 3 * 24000:
        raise ValueError('Necesitamos al menos 3 segundos de audio válido.')
    peak = float(np.max(np.abs(audio)))
    if peak < 0.005 or np.sqrt(np.mean(audio ** 2)) < 0.001:
        raise ValueError('La grabación está en silencio o tiene un volumen demasiado bajo.')
    return audio / max(1.0, peak / 0.95)


class MP3Encoder:
    def __init__(self, sr):
        self.output = io.BytesIO()
        self.container = av.open(self.output, mode='w', format='mp3', options={'write_xing': '0', 'id3v2_version': '0'})
        self.stream = self.container.add_stream('libmp3lame', rate=sr)
        self.stream.layout = 'mono'
        self.stream.bit_rate = 96000
        self.sr, self.samples, self.cursor, self.closed = sr, 0, 0, False

    def take(self):
        data = self.output.getvalue()
        chunk = data[self.cursor:]
        self.cursor = len(data)
        return chunk

    def encode(self, samples):
        samples = np.asarray(samples, dtype=np.float32).reshape(1, -1)
        if not samples.size:
            return b''
        frame = av.AudioFrame.from_ndarray(samples, format='fltp', layout='mono')
        frame.sample_rate, frame.pts = self.sr, self.samples
        self.samples += samples.shape[-1]
        for packet in self.stream.encode(frame):
            self.container.mux(packet)
        return self.take()

    def finish(self):
        if self.closed:
            return b''
        try:
            for packet in self.stream.encode(None):
                self.container.mux(packet)
            self.container.close()
        finally:
            self.closed = True
        return self.take()
