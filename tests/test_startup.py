import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from voz_estudio import app as module, storage


class StartupTests(unittest.TestCase):
    def test_loading_is_visible_without_blocking_the_application(self):
        entered, release = threading.Event(), threading.Event()
        class SlowEngine:
            state, mode, error = 'idle', None, None
            def load(self):
                entered.set()
                release.wait(5)
                self.mode, self.state = 'cuda', 'ready'
        engine = SlowEngine()
        with tempfile.TemporaryDirectory() as directory, patch.object(storage, 'DATA', Path(directory)), patch.object(module, 'engine', engine):
            try:
                with TestClient(module.app) as client:
                    self.assertTrue(entered.wait(2))
                    self.assertEqual(client.get('/').status_code, 200)
                    self.assertEqual(client.get('/api/status').json()['engine'], 'loading')
                    release.set()
                    deadline = time.monotonic()+2
                    while engine.state != 'ready' and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.assertEqual(client.get('/api/status').json()['engine'], 'ready')
            finally:
                release.set()
