import json
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from voz_estudio import app as module
from voz_estudio import storage


class FakeEngine:
    state, mode, error = 'idle', None, None
    def __init__(self):
        self.used_voices = []
    def load(self, key='base06'):
        self.state, self.mode = 'ready', 'cpu'
        self.model_key=key
    def unload(self):
        self.state,self.model_key='idle',None
    def generate(self, text, voice, options=None):
        self.used_voices.append(voice['id'] if voice else 'custom')
        for _ in range(3):
            time.sleep(0.02)
            yield (np.sin(np.arange(2400) * 0.08) * .1).astype(np.float32), 24000, {}


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.old_data, self.old_engine = storage.DATA, module.engine
        storage.DATA = Path(self.temporary.name)
        module.engine = FakeEngine()
        self.client_context = TestClient(module.app, base_url='http://localhost')
        self.client = self.client_context.__enter__()
        self.voice = self.add_voice('../César <persona>')

    def tearDown(self):
        deadline = time.monotonic() + 5
        while module.cancel_flags and time.monotonic() < deadline:
            time.sleep(.01)
        self.client_context.__exit__(None, None, None)
        storage.DATA, module.engine = self.old_data, self.old_engine
        self.temporary.cleanup()

    def add_voice(self, name):
        identifier = uuid.uuid4().hex
        path = storage.voice_path(identifier)
        path.parent.mkdir()
        sf.write(path.parent / 'reference.wav', np.zeros(24000, dtype=np.float32), 24000)
        voice = {'id': identifier, 'name': name, 'slug': storage.slug(name), 'status': 'ready',
                 'created_at': storage.now().isoformat(), 'transcript': 'Referencia', 'duration_s': 1}
        storage.write_json(path, voice)
        return voice

    def wait_record(self, identifier):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            data = self.client.get('/api/recordings/' + identifier).json()
            if data['status'] in ('completed', 'error', 'cancelled'):
                return data
            time.sleep(.02)
        self.fail('La generación no terminó.')

    def create(self, voice=None, text='Hola. Este es el texto completo que debe conservarse.'):
        response = self.client.post('/api/recordings', json={'voice_id': (voice or self.voice)['id'], 'text': text})
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()

    def test_recording_has_text_voice_date_audio_and_json(self):
        record = self.create()
        done = self.wait_record(record['id'])
        self.assertEqual(done['status'], 'completed')
        self.assertIn('cesar-persona_', done['filename'])
        self.assertIn(storage.now().strftime('%Y-%m-%d'), done['filename'])
        self.assertEqual(module.engine.used_voices, [self.voice['id']])
        audio = self.client.get(f"/api/recordings/{record['id']}/audio?download=true")
        self.assertEqual(audio.status_code, 200)
        self.assertGreater(len(audio.content), 100)
        metadata = self.client.get(f"/api/recordings/{record['id']}/json").json()
        self.assertEqual(metadata['text'], record['text'])
        self.assertEqual(metadata['voice_name'], self.voice['name'])
        exported = self.client.get('/api/export').json()
        self.assertEqual(exported['recordings'][0]['text'], record['text'])
        self.assertEqual(exported['schema_version'], 1)

    def test_distinct_voice_selection_and_no_filename_collision(self):
        second = self.add_voice(self.voice['name'])
        first_record, second_record = self.create(), self.create(second)
        self.assertNotEqual(first_record['filename'], second_record['filename'])
        self.wait_record(first_record['id']); self.wait_record(second_record['id'])
        self.assertEqual(module.engine.used_voices, [self.voice['id'], second['id']])
        response = self.client.get('/api/recordings', params={'voice_id': second['id']}).json()
        self.assertEqual(response['total'], 1)
        self.assertEqual(response['items'][0]['voice_id'], second['id'])

    def test_empty_text_invalid_id_and_cross_origin_rejected(self):
        self.assertEqual(self.client.post('/api/recordings', json={'voice_id': self.voice['id'], 'text':'   '}).status_code, 422)
        self.assertEqual(self.client.post('/api/recordings', json={'voice_id':'../bad', 'text':'Hola'}).status_code, 400)
        self.assertEqual(self.client.get('/api/recordings/not-an-id').status_code, 400)
        self.assertEqual(self.client.post('/api/recordings', json={'voice_id':self.voice['id'],'text':'Hola'}, headers={'Origin':'https://external.example'}).status_code, 403)
        self.assertEqual(self.client.get('/api/recordings').json()['total'], 0)

    def test_cancel_keeps_metadata(self):
        record = self.create(text='Texto que también debe conservarse al cancelar.')
        response = self.client.post(f"/api/recordings/{record['id']}/cancel")
        self.assertEqual(response.status_code, 200)
        done = self.wait_record(record['id'])
        self.assertEqual(done['status'], 'cancelled')
        self.assertEqual(done['text'], record['text'])

    def test_bad_upload_is_an_error_not_a_ready_voice(self):
        response = self.client.post('/api/voices', data={'name':'Muestra inválida'}, files={'audio':('test.wav',b'not a sound file','audio/wav')})
        self.assertEqual(response.status_code, 202)
        identifier = response.json()['id']
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            voice = storage.read_json(storage.voice_path(identifier))
            if voice['status'] == 'error':
                break
            time.sleep(.02)
        self.assertEqual(voice['status'], 'error')
        self.assertTrue(voice['error'])

    def test_interrupted_recording_is_recovered_with_text(self):
        identifier = uuid.uuid4().hex
        path = storage.folder('recordings') / f'test_{identifier}.json'
        storage.write_json(path, {'id':identifier,'created_at':storage.now().isoformat(),'status':'generating','text':'Conservar este texto.'})
        storage.recover_interrupted()
        recovered = storage.read_json(path)
        self.assertEqual(recovered['status'], 'error')
        self.assertEqual(recovered['text'], 'Conservar este texto.')

    def test_transient_windows_lock_does_not_lose_json(self):
        path = storage.DATA / 'retry.json'
        original_replace = storage.os.replace
        attempts = []
        def briefly_locked(source, target):
            attempts.append(1)
            if len(attempts) < 3:
                raise PermissionError('Temporary Windows sharing violation')
            return original_replace(source, target)
        with patch.object(storage.os, 'replace', side_effect=briefly_locked):
            storage.write_json(path, {'text': 'El texto se conserva.'})
        self.assertEqual(storage.read_json(path)['text'], 'El texto se conserva.')
        self.assertFalse(list(storage.DATA.glob('*.tmp')))


if __name__ == '__main__':
    unittest.main()
