"""Synthetic fixtures only; no private source, source token, or real history."""
import copy
import hashlib
import json
import os
import stat
import sys
import tempfile
import unittest
import shutil
import uuid
import zipfile
import io
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_static_site as verifier
import download_approved_artifact as download


class PublicationTests(unittest.TestCase):
    def setUp(self):
        # Avoid Python 3.13's Windows 0700 ACL behavior in sandboxed runners.
        base = Path(tempfile.gettempdir()).resolve()
        self.root = base / ('cot-public-test-' + uuid.uuid4().hex)
        self.root.mkdir(mode=0o755)
        def cleanup():
            if self.root.resolve().parent != base or not self.root.name.startswith('cot-public-test-'):
                raise ValueError('Unsafe test cleanup path')
            shutil.rmtree(self.root)
        self.addCleanup(cleanup)
        self.site = self.root / 'fixture'
        self.site.mkdir()
        self.payloads = {name: b'{}' for name in verifier.FILES}
        self.payloads['index.html'] = b'<html>synthetic fixture</html>'
        self.payloads['data-source.js'] = b'/* synthetic fixture */'
        self.payloads['.nojekyll'] = b''
        self.manifest = {
            'history_sha256': verifier.APPROVED_HISTORY, 'record_count': 910,
            'files': {name: verifier.sha256(self.payloads['data/' + name]) for name in verifier.DATA},
            'assets': {name: verifier.sha256(self.payloads[name]) for name in verifier.ASSETS},
        }
        self.write_manifest()
        for name, data in self.payloads.items():
            target = self.site / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.head = 'a' * 40
        self.name = 'static-site-preview-' + self.head
        self.digest = 'b' * 64
        self.run = {'id': 123, 'repository': {'id': download.REPOSITORY_ID},
                    'head_repository': {'id': download.REPOSITORY_ID}, 'path': download.WORKFLOW_PATH,
                    'head_branch': 'main', 'event': 'workflow_dispatch', 'status': 'completed',
                    'conclusion': 'success', 'head_sha': self.head}
        self.artifact = {'id': 456, 'name': self.name, 'expired': False, 'size_in_bytes': 1000,
                         'digest': 'sha256:' + self.digest, 'workflow_run': {
                             'id': 123, 'repository_id': download.REPOSITORY_ID,
                             'head_repository_id': download.REPOSITORY_ID, 'head_sha': self.head}}

    def write_manifest(self):
        encoded = json.dumps(self.manifest).encode()
        self.payloads['data/generation.json'] = encoded
        path = self.site / 'data/generation.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded)

    def verify(self):
        return verifier.verify_site(self.site, verifier.APPROVED_HISTORY)

    def archive(self, additions=()):
        archive = self.root / 'fixture.zip'
        with zipfile.ZipFile(archive, 'w') as zipped:
            for name, data in self.payloads.items():
                zipped.writestr(name, data)
            for name, data in additions:
                zipped.writestr(name, data)
        return archive

    def extract(self, archive, digest=None):
        return verifier.extract_verified_archive(archive, self.root / 'extracted',
            digest or verifier.sha256(archive.read_bytes()), verifier.APPROVED_HISTORY)

    def test_valid_site_and_archive(self):
        self.assertEqual(self.verify()['record_count'], 910)
        self.assertEqual(self.extract(self.archive())['record_count'], 910)
        self.assertEqual({p.relative_to(self.root / 'extracted').as_posix()
                          for p in (self.root / 'extracted').rglob('*') if p.is_file()}, verifier.FILES)

    def test_reject_extra_private_files(self):
        for name in ('cot.db', 'backup.zip', '.env', 'api.py', 'history/records-raw.json'):
            with self.subTest(name=name):
                target = self.site / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'private')
                with self.assertRaises(ValueError): self.verify()
                target.unlink()
                if target.parent != self.site: target.parent.rmdir()

    def test_reject_missing_file(self):
        (self.site / 'data/cot/EUR.json').unlink()
        with self.assertRaises(ValueError): self.verify()

    def test_reject_corrupt_file(self):
        (self.site / 'index.html').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.verify()

    def test_reject_wrong_history(self):
        self.manifest['history_sha256'] = '0' * 64
        self.write_manifest()
        with self.assertRaises(ValueError): self.verify()
        with self.assertRaises(ValueError): verifier.verify_site(self.site, '0' * 64)

    def test_reject_invalid_count(self):
        for count in (909, '910', True, None):
            self.manifest['record_count'] = count
            self.write_manifest()
            with self.assertRaises(ValueError): self.verify()

    def test_reject_manifest_inventory_or_hash(self):
        self.manifest['assets']['index.html'] = 'invalid'
        self.write_manifest()
        with self.assertRaises(ValueError): self.verify()
        self.manifest['files']['private.db'] = 'a' * 64
        self.write_manifest()
        with self.assertRaises(ValueError): self.verify()

    def test_reject_duplicate_json_keys(self):
        target = self.site / 'data/generation.json'
        encoded = target.read_text()
        target.write_text(encoded[:-1] + ', "record_count": 910}')
        with self.assertRaises(ValueError): self.verify()

    def test_reject_zip_traversal_and_private_file_before_writes(self):
        for name in ('../escape', '/absolute', 'data/../escape', 'data\\escape', 'cot.db'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError): self.extract(self.archive([(name, b'private')]))
                self.assertFalse((self.root / 'extracted').exists())

    def test_reject_zip_duplicate(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            archive = self.archive([('index.html', b'changed')])
        with self.assertRaises(ValueError): self.extract(archive)
        self.assertFalse((self.root / 'extracted').exists())

    def test_reject_zip_symlink(self):
        archive = self.archive()
        with zipfile.ZipFile(archive, 'a') as zipped:
            link = zipfile.ZipInfo('data/')
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            zipped.writestr(link, b'../../private')
        with self.assertRaises(ValueError): self.extract(archive)

    def test_reject_unapproved_archive_with_rewritten_manifest(self):
        archive = self.archive()
        approved = verifier.sha256(archive.read_bytes())
        self.payloads['index.html'] = b'<html>unreviewed content</html>'
        self.manifest['assets']['index.html'] = verifier.sha256(self.payloads['index.html'])
        self.write_manifest()
        with self.assertRaises(ValueError): self.extract(self.archive(), approved)

    def test_reject_oversized_archive(self):
        archive = self.archive()
        with patch.object(verifier, 'MAX_BYTES', 10):
            with self.assertRaises(ValueError): self.extract(archive)

    def test_reject_existing_destination(self):
        (self.root / 'extracted').mkdir()
        with self.assertRaises(ValueError): self.extract(self.archive())

    def test_reject_hardlinks(self):
        target = self.site / 'index.html'
        os.link(target, self.root / 'linked')
        with self.assertRaises(ValueError): self.verify()

    def test_valid_input_and_provenance(self):
        download.validate_inputs('123', self.name, verifier.APPROVED_HISTORY, self.digest)
        self.assertEqual(download.select_artifact(self.run, [self.artifact], '123', self.name, self.digest)['id'], 456)

    def test_reject_input_injection(self):
        for run_id, name, history, digest in (
            ('123; echo secret', self.name, verifier.APPROVED_HISTORY, self.digest),
            ('123', '*', verifier.APPROVED_HISTORY, self.digest),
            ('123', self.name, '0' * 64, self.digest),
            ('123', self.name, verifier.APPROVED_HISTORY, 'sha256:' + self.digest)):
            with self.assertRaises(ValueError): download.validate_inputs(run_id, name, history, digest)

    def test_reject_untrusted_run(self):
        for key, value in (('id', 999), ('path', '.github/workflows/other.yml'),
                           ('head_branch', 'feature'), ('event', 'pull_request'),
                           ('status', 'in_progress'), ('conclusion', 'failure'),
                           ('head_repository', {'id': 999})):
            run = copy.deepcopy(self.run)
            run[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                download.select_artifact(run, [self.artifact], '123', self.name, self.digest)

    def test_reject_missing_duplicate_expired_or_wrong_artifact(self):
        candidates = [[], [self.artifact, self.artifact]]
        for key, value in (('expired', True), ('digest', 'sha256:' + 'c' * 64),
                           ('size_in_bytes', verifier.MAX_BYTES + 1), ('name', 'other'),
                           ('workflow_run', {'id': 999})):
            artifact = copy.deepcopy(self.artifact)
            artifact[key] = value
            candidates.append([artifact])
        for artifacts in candidates:
            with self.assertRaises(ValueError): download.select_artifact(self.run, artifacts, '123', self.name, self.digest)

    def test_api_credential_bound_to_fixed_repository(self):
        request = download.api_request(download.API + '/runs/123', 'synthetic-token')
        self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-token')
        with self.assertRaises(ValueError): download.api_request('https://example.com', 'synthetic-token')

    def test_signed_download_does_not_forward_token(self):
        api = MagicMock()
        api.open.side_effect = urllib.error.HTTPError('https://api.github.com', 302, 'redirect',
            {'Location': 'https://signed-storage.example/approved.zip'}, None)
        storage = MagicMock()
        storage.open.return_value.__enter__.return_value = io.BytesIO(b'zip-fixture')
        with patch.object(download.urllib.request, 'build_opener', side_effect=[api, storage]):
            output = self.root / 'download.zip'
            download.download_archive(456, 'synthetic-token', output)
        self.assertEqual(api.open.call_args.args[0].get_header('Authorization'), 'Bearer synthetic-token')
        self.assertIsNone(storage.open.call_args.args[0].get_header('Authorization'))
        self.assertEqual(output.read_bytes(), b'zip-fixture')

    def test_reject_insecure_archive_redirect(self):
        for url in ('http://storage.example/file', 'https://user:password@storage.example/file'):
            api = MagicMock()
            api.open.side_effect = urllib.error.HTTPError('https://api.github.com', 302, 'redirect',
                {'Location': url}, None)
            with patch.object(download.urllib.request, 'build_opener', return_value=api):
                with self.assertRaises(ValueError): download.download_archive(456, 'synthetic-token', self.root / 'bad.zip')
            self.assertFalse((self.root / 'bad.zip').exists())

    def test_signed_download_size_limit(self):
        api = MagicMock()
        api.open.side_effect = urllib.error.HTTPError('https://api.github.com', 302, 'redirect',
            {'Location': 'https://storage.example/file'}, None)
        storage = MagicMock()
        storage.open.return_value.__enter__.return_value = io.BytesIO(b'oversized')
        with patch.object(download.urllib.request, 'build_opener', side_effect=[api, storage]), patch.object(download, 'MAX_BYTES', 1):
            with self.assertRaises(ValueError): download.download_archive(456, 'synthetic-token', self.root / 'oversized.zip')


if __name__ == '__main__':
    unittest.main()
