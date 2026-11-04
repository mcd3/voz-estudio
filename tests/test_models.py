import io
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import Mock, patch
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from voz_estudio import app as module, storage
from test_app import FakeEngine


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'DATA',Path(self.temp.name)),patch.object(module,'engine',FakeEngine()),
                      patch.object(module,'model_path',return_value=Path('model'))]
        for p in self.patches:p.start()
        self.context=TestClient(module.app);self.client=self.context.__enter__()
        self.voice_id=uuid.uuid4().hex
        storage.write_json(storage.voice_path(self.voice_id),dict(id=self.voice_id,name='Prueba',slug='prueba',
              status='ready',created_at=storage.now().isoformat(),transcript='Referencia'))

    def tearDown(self):
        deadline=time.monotonic()+5
        while (module.cancel_flags or module.design_jobs) and time.monotonic()<deadline:time.sleep(.01)
        self.context.__exit__(None,None,None)
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def wait(self,identifier):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            record=self.client.get('/api/recordings/'+identifier).json()
            if record['status'] in ('completed','error'):return record
            time.sleep(.01)
        self.fail('Generation did not finish')

    def test_catalog_lists_five_models_ten_languages_and_auto(self):
        catalog=self.client.get('/api/catalog').json()
        self.assertEqual(len(catalog['models']),5)
        self.assertEqual(len(catalog['languages']),11)
        self.assertEqual(len(catalog['speakers']),9)
        self.assertFalse(next(m for m in catalog['models'] if m['id']=='custom06')['instructions'])

    def test_base17_language_and_sampling_are_saved(self):
        response=self.client.post('/api/recordings',json=dict(voice_id=self.voice_id,text='Hello, this is an English test.',
                   model='base17',language='English',seed=123,temperature=.7))
        self.assertEqual(response.status_code,202,response.text)
        record=self.wait(response.json()['id'])
        self.assertEqual(record['status'],'completed',record)
        self.assertEqual((record['model'],record['language'],record['seed']),('base17','English',123))
        self.assertIn('1.7B-Base',record['engine'])
        self.assertIn('rtf',record)

    def test_custom_requires_no_registered_voice_and_styles_are_validated(self):
        payload=dict(text='Bonjour, voici une nouvelle voix.',model='custom17',language='French',speaker='Ryan',instruct='Calm')
        response=self.client.post('/api/recordings',json=payload)
        self.assertEqual(response.status_code,202,response.text)
        record=self.wait(response.json()['id'])
        self.assertEqual(record['status'],'completed',record)
        self.assertIsNone(record['voice_id'])
        payload['model']='custom06'
        self.assertEqual(self.client.post('/api/recordings',json=payload).status_code,400)
        payload['instruct']='';payload['speaker']='not-a-speaker'
        self.assertEqual(self.client.post('/api/recordings',json=payload).status_code,400)
        payload['speaker']='Ryan';payload['language']='Klingon'
        self.assertEqual(self.client.post('/api/recordings',json=payload).status_code,400)

    def test_comparison_uses_same_settings_and_evaluation_is_persistent(self):
        response=self.client.post('/api/comparisons',json=dict(voice_id=self.voice_id,text='El mismo texto para los dos modelos.',language='Spanish',seed=99))
        self.assertEqual(response.status_code,202,response.text)
        group=response.json()
        items=[self.wait(identifier) for identifier in group['recordings']]
        self.assertEqual([r['model'] for r in items],['base06','base06','base17','base17'])
        self.assertEqual([r['force_reload'] for r in items],[True,False,True,False])
        self.assertTrue(all(r['seed']==99 and r['language']=='Spanish' for r in items))
        self.assertEqual([r['trial'] for r in items],[1,2,1,2])
        record=items[1]
        evaluation=dict(naturalness=4,intelligibility=5,similarity=4,notes='Mejor pronunciación en esta frase.')
        self.assertEqual(self.client.post(f"/api/recordings/{record['id']}/evaluation",json=evaluation).status_code,200)
        exported=self.client.get('/api/comparisons/'+group['id']+'/json').json()
        self.assertEqual(exported['items'][1]['evaluation']['notes'],evaluation['notes'])
        self.assertEqual(self.client.post(f"/api/recordings/{record['id']}/evaluation",json={'naturalness':0}).status_code,422)

    def test_reference_language_is_passed_to_whisper(self):
        model=Mock()
        def transcribe(*args,**kwargs):
            return iter([SimpleNamespace(start=0,end=4,text='This is the reference text.')]),SimpleNamespace(language='en')
        model.transcribe.side_effect=transcribe
        fake=SimpleNamespace(WhisperModel=Mock(return_value=model))
        audio=io.BytesIO();sf.write(audio,np.sin(np.arange(96000)*.04).astype('float32')*.1,24000,format='WAV')
        with patch.dict(sys.modules,{'faster_whisper':fake}):
            response=self.client.post('/api/voices',data=dict(name='English reference',language='English'),files={'audio':('reference.wav',audio.getvalue(),'audio/wav')})
            identifier=response.json()['id'];deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                voice=storage.read_json(storage.voice_path(identifier))
                if voice['status'] in ('ready','error'):break
                time.sleep(.01)
            self.assertEqual(voice['status'],'ready',voice)
            self.assertEqual(model.transcribe.call_args.kwargs['language'],'en')
            self.assertEqual(voice['transcription_language'],'en')
