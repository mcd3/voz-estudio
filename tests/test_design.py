import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from voz_estudio import app as module, storage
from test_app import FakeEngine


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.data=patch.object(storage,'DATA',Path(self.temp.name));self.data.start()
        self.engine=patch.object(module,'engine',FakeEngine());self.engine.start()
        self.client_context=TestClient(module.app)
        self.client=self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None,None,None)
        self.engine.stop();self.data.stop();self.temp.cleanup()

    def test_missing_model_and_blank_description(self):
        payload=dict(name='Narrador',description='Una voz grave y cálida',text='Este texto sirve para crear una muestra de una voz nueva.')
        with patch.object(module,'model_path',return_value=None):
            self.assertEqual(self.client.post('/api/designs',json=payload).status_code,409)
        payload['description']=' '*12
        self.assertEqual(self.client.post('/api/designs',json=payload).status_code,422)
        self.assertEqual(self.client.get('/api/designs/not-valid/audio').status_code,400)

    def test_preview_save_is_idempotent_and_voice_can_be_cloned(self):
        def create_preview(identifier):
            path=module.design_path(identifier)
            sf.write(path.parent/'preview.wav',np.sin(np.arange(72000)*.05).astype('float32')*.1,24000)
            storage.update(path,status='ready',duration_s=3,sample_rate=24000)
            module.design_jobs.discard(identifier)
        payload=dict(name='Narrador nuevo',description='Una voz cálida con acento castellano',text='Este es el texto que se conservará como referencia para clonar la nueva voz.')
        with patch.object(module,'model_path',return_value=Path('model')),patch.object(module,'perform_design',side_effect=create_preview):
            response=self.client.post('/api/designs',json=payload)
            self.assertEqual(response.status_code,202,response.text)
            identifier=response.json()['id']
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if self.client.get('/api/designs/'+identifier).json()['status']=='ready':break
                time.sleep(.01)
            self.assertEqual(self.client.get(f'/api/designs/{identifier}/audio').status_code,200)
            first=self.client.post(f'/api/designs/{identifier}/save').json()
            second=self.client.post(f'/api/designs/{identifier}/save').json()
            self.assertEqual(first['id'],second['id'])
            self.assertEqual(first['transcript'],payload['text'])
            self.assertEqual(first['description'],payload['description'])
            self.assertEqual(len(self.client.get('/api/voices').json()),1)
            record=self.client.post('/api/recordings',json=dict(voice_id=first['id'],text='Ahora hablamos con esta voz creada.')).json()
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                done=self.client.get('/api/recordings/'+record['id']).json()
                if done['status'] in ('completed','error'):break
                time.sleep(.02)
            self.assertEqual(done['status'],'completed',done)

    def test_interrupted_preview_becomes_retryable_error(self):
        import uuid
        path=module.design_path(uuid.uuid4().hex)
        storage.write_json(path,dict(status='queued',created_at='2026-11-04',id=path.parent.name))
        with TestClient(module.app) as client:
            self.assertEqual(client.get('/api/designs/'+path.parent.name).json()['status'],'error')

    def test_shutdown_terminates_the_active_design_worker(self):
        from unittest.mock import Mock
        child=Mock()
        child.poll.return_value=None
        module.design_processes.add(child)
        try:
            with TestClient(module.app):
                pass
            child.terminate.assert_called_once()
        finally:
            module.design_processes.discard(child)

    def test_worker_process_is_reaped_and_clone_engine_prepared_again(self):
        import uuid
        identifier=uuid.uuid4().hex
        path=module.design_path(identifier)
        storage.write_json(path,dict(id=identifier,status='queued'))
        class Child:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def wait(self,timeout):
                storage.update(path,status='ready')
                return 0
        child=Child()
        module.design_jobs.add(identifier)
        with patch.object(module.engine,'unload',create=True),patch.object(module.subprocess,'Popen',return_value=child):
            module.perform_design(identifier)
        self.assertEqual(storage.read_json(path)['status'],'ready')
        self.assertEqual(module.engine.state,'ready')
        self.assertNotIn(identifier,module.design_jobs)
        self.assertNotIn(child,module.design_processes)
