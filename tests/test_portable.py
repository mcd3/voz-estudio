"""Packaging integrity and extraction checks, without downloading models."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts' / 'portable'


def module(name):
    spec = importlib.util.spec_from_file_location('portable_' + name, SCRIPTS / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


build, extract = module('build'), module('extract')


class PortableTests(unittest.TestCase):
    def fixture(self, folder, member='VozEstudio/app/example.txt'):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr(member, 'contenido de prueba')
        contents = buffer.getvalue()
        writer = build.SplitWriter(folder, 'package.zip', limit=37)
        writer.write(contents[:29])
        writer.write(contents[29:])
        parts = writer.finish()
        manifest = dict(directory='VozEstudio', parts=parts, archive_bytes=len(contents),
                        archive_sha256=hashlib.sha256(contents).hexdigest())
        (folder / 'release-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(p['bytes'] <= 37 for p in parts))
        self.assertEqual(writer.archive_hash.hexdigest(), manifest['archive_sha256'])
        return parts

    def test_split_join_extract_and_preserve_existing_data(self):
        with tempfile.TemporaryDirectory(prefix='voz portable ') as temporary:
            folder = Path(temporary)
            self.fixture(folder)
            extract.extract(folder)
            self.assertEqual((folder / 'VozEstudio/app/example.txt').read_text(), 'contenido de prueba')
            self.assertFalse((folder / 'VozEstudio.zip').exists())
            with self.assertRaisesRegex(RuntimeError, 'ya existe'):
                extract.extract(folder)
            self.assertTrue((folder / 'VozEstudio/app/example.txt').exists())

    def test_corrupt_part_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            parts = self.fixture(folder)
            path = folder / parts[0]['name']
            path.write_bytes(b'x' * path.stat().st_size)
            with self.assertRaisesRegex(RuntimeError, 'huella'):
                extract.extract(folder)
            self.assertFalse((folder / 'VozEstudio').exists())
            self.assertFalse((folder / 'VozEstudio.zip').exists())

    def test_zip_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            self.fixture(folder, 'VozEstudio/../outside.txt')
            with self.assertRaisesRegex(RuntimeError, 'Ruta inesperada'):
                extract.extract(folder)
            self.assertFalse((folder / 'outside.txt').exists())


if __name__ == '__main__':
    unittest.main()
