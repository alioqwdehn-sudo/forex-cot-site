"""Public, independently implemented verifier for the reviewed static contract.

Never imports, builds, or executes anything from the private artifact.
"""
import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

APPROVED_HISTORY = '068962973edc3e7586316cea3c54871efdb12b8441a9790309a9dbdf1318123b'
CURRENCIES = ('AUD', 'GBP', 'CAD', 'EUR', 'JPY', 'NZD', 'CHF', 'BRL', 'MXN', 'ZAR')
PAIRS = ('EUR-USD', 'GBP-USD', 'AUD-USD', 'NZD-USD', 'USD-CAD', 'USD-CHF', 'USD-JPY', 'USD-MXN', 'USD-BRL', 'USD-ZAR')
DATA = {'currencies.json', 'pairs.json', 'health.json', 'ready.json'} | {f'cot/{c}.json' for c in CURRENCIES} | {f'pair/{p}.json' for p in PAIRS}
ASSETS = {'index.html', 'data-source.js', '.nojekyll'}
FILES = ASSETS | {f'data/{p}' for p in DATA} | {'data/generation.json'}
DIRECTORIES = {'data', 'data/cot', 'data/pair'}
MAX_BYTES = 100 * 1024 * 1024


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def checksum(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Expected a lowercase SHA-256')
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def verify_site(directory, expected_history_sha256):
    if checksum(expected_history_sha256) != APPROVED_HISTORY:
        raise ValueError('History is not approved by the publishing policy')
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Site must be a real directory')
    actual = set()
    total = 0
    for path in root.rglob('*'):
        name = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError('Links are forbidden')
        if stat.S_ISDIR(mode):
            if name not in DIRECTORIES:
                raise ValueError('Unexpected directory')
        elif stat.S_ISREG(mode):
            if name not in FILES or path.stat().st_nlink != 1:
                raise ValueError('Unexpected file or hard link')
            total += path.stat().st_size
            actual.add(name)
        else:
            raise ValueError('Special files are forbidden')
    if actual != FILES or total > MAX_BYTES:
        raise ValueError('Incomplete or oversized static site')
    manifest = json.loads((root / 'data/generation.json').read_bytes(), object_pairs_hook=unique_object)
    if not isinstance(manifest, dict) or manifest.get('history_sha256') != expected_history_sha256:
        raise ValueError('History does not match approval')
    data, assets = manifest.get('files'), manifest.get('assets')
    if not isinstance(data, dict) or set(data) != DATA or not isinstance(assets, dict) or set(assets) != ASSETS:
        raise ValueError('Invalid manifest inventory')
    count = manifest.get('record_count')
    if type(count) is not int or count < 910:
        raise ValueError('Full seed history is required')
    hashes = {f'data/{name}': digest for name, digest in data.items()} | assets
    for name, digest in hashes.items():
        if sha256((root / name).read_bytes()) != checksum(digest):
            raise ValueError('File checksum mismatch')
    if (root / '.nojekyll').read_bytes() != b'':
        raise ValueError('Unexpected content in .nojekyll')
    return manifest


def extract_verified_archive(archive, destination, expected_archive_sha256, expected_history_sha256):
    """Inspect every member before writing; never use extractall on private ZIPs."""
    archive, destination = Path(archive), Path(destination)
    if archive.stat().st_size > MAX_BYTES or sha256(archive.read_bytes()) != checksum(expected_archive_sha256):
        raise ValueError('Archive checksum mismatch or size limit exceeded')
    if destination.exists() or destination.is_symlink():
        raise ValueError('Destination must be new')
    with zipfile.ZipFile(archive) as zipped:
        if zipped.comment:
            raise ValueError('Archive comments are forbidden')
        seen, files, total = set(), set(), 0
        for member in zipped.infolist():
            name = member.filename
            mode = member.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if name in seen or member.orig_filename != name or member.comment or member.flag_bits & 1:
                raise ValueError('Duplicate, malformed, commented, or encrypted ZIP entry')
            seen.add(name)
            if member.is_dir():
                if name not in {d + '/' for d in DIRECTORIES} or kind not in (0, stat.S_IFDIR) or member.file_size:
                    raise ValueError('Unexpected ZIP directory')
            else:
                if name not in FILES or kind not in (0, stat.S_IFREG):
                    raise ValueError('Unexpected ZIP file or link')
                files.add(name)
                total += member.file_size
            if total > MAX_BYTES or len(seen) > len(FILES) + len(DIRECTORIES):
                raise ValueError('Archive exceeds static site limits')
        if files != FILES:
            raise ValueError('ZIP inventory does not match static allowlist')
        destination.mkdir(parents=True)
        for member in zipped.infolist():
            if not member.is_dir():
                target = destination / member.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as output:
                    output.write(zipped.read(member))
    return verify_site(destination, expected_history_sha256)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--expected-history-sha256', required=True)
    args = parser.parse_args()
    try:
        verify_site(args.site, args.expected_history_sha256)
    except (ValueError, OSError, KeyError, TypeError):
        raise SystemExit('Static verification failed; no artifact was published.')
    print('Static inventory, history approval, and file checksums verified.')
