"""Download exactly one approved private Actions artifact; never check out source."""
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from verify_static_site import MANUAL_APPROVED_HISTORY, MAX_BYTES, checksum, extract_verified_archive, sha256

REPOSITORY = 'alioqwdehn-sudo/forex-cot-platform'
REPOSITORY_ID = 1410262806
WORKFLOW_PATH = '.github/workflows/static-pages.yml'
API = f'https://api.github.com/repos/{REPOSITORY}/actions'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_request(url, token):
    if not url.startswith(API + '/'):
        raise ValueError('Unexpected API endpoint')
    return urllib.request.Request(url, headers={
        'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'forex-cot-approved-pages',
    })


def api_json(url, token):
    with urllib.request.build_opener(NoRedirect).open(api_request(url, token), timeout=60) as response:
        data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('API response exceeds limit')
        return json.loads(data)


def validate_inputs(run_id, artifact_name, history, archive_hash):
    if not re.fullmatch(r'[1-9][0-9]{0,19}', run_id):
        raise ValueError('A numeric source run ID is required')
    if not re.fullmatch(r'static-site-preview-[0-9a-f]{40}', artifact_name):
        raise ValueError('An exact static preview artifact name is required')
    if checksum(history) != MANUAL_APPROVED_HISTORY:
        raise ValueError('History is not approved')
    checksum(archive_hash)


def select_artifact(run, artifacts, run_id, artifact_name, archive_hash, *, workflow_path=WORKFLOW_PATH, events=('workflow_dispatch',), automatic=False, artifact_prefix='automatic'):
    if artifact_prefix not in ('automatic','preflight'): raise ValueError('Invalid artifact mode')
    if (run.get('id') != int(run_id) or run.get('repository', {}).get('id') != REPOSITORY_ID
            or run.get('head_repository', {}).get('id') != REPOSITORY_ID
            or run.get('path') != workflow_path or run.get('head_branch') != 'main'
            or run.get('event') not in events or run.get('status') != 'completed'
            or run.get('conclusion') != 'success'):
        raise ValueError('Source run provenance or status is invalid')
    head = run.get('head_sha', '')
    if not re.fullmatch('[0-9a-f]{40}', head):
        raise ValueError('Invalid source commit')
    expected_name = f'{artifact_prefix}-site-{run_id}-{head}' if automatic else f'static-site-preview-{head}'
    if artifact_name != expected_name:
        raise ValueError('Artifact name does not match the source commit')
    matches = [a for a in artifacts if a.get('name') == artifact_name]
    if len(matches) != 1:
        raise ValueError('Exactly one selected artifact must exist')
    artifact = matches[0]
    provenance = artifact.get('workflow_run', {})
    if (artifact.get('expired') is not False or type(artifact.get('id')) is not int
            or type(artifact.get('size_in_bytes')) is not int
            or not 0 < artifact['size_in_bytes'] <= MAX_BYTES
            or provenance.get('id') != int(run_id)
            or provenance.get('repository_id') != REPOSITORY_ID
            or provenance.get('head_repository_id') != REPOSITORY_ID
            or provenance.get('head_sha') != head
            or artifact.get('digest') != 'sha256:' + archive_hash):
        raise ValueError('Artifact provenance, expiry, size, or approved digest is invalid')
    return artifact


def download_archive(artifact_id, token, output):
    # GitHub returns a signed storage URL. Never forward Authorization to it.
    try:
        urllib.request.build_opener(NoRedirect).open(
            api_request(f'{API}/artifacts/{artifact_id}/zip', token), timeout=60)
    except urllib.error.HTTPError as error:
        if error.code != 302:
            raise ValueError('Artifact archive API request failed') from None
        location = error.headers.get('Location', '')
        error.close()
    else:
        raise ValueError('Expected the documented archive redirect')
    parsed = urllib.parse.urlsplit(location)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Unsafe archive redirect')
    request = urllib.request.Request(location, headers={'User-Agent': 'forex-cot-approved-pages'})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=60) as response, output.open('xb') as target:
        size = 0
        while block := response.read(1024 * 1024):
            size += len(block)
            if size > MAX_BYTES:
                raise ValueError('Archive download exceeds limit')
            target.write(block)


def main():
    run_id = os.environ.get('SOURCE_RUN_ID', '')
    name = os.environ.get('ARTIFACT_NAME', '')
    history = os.environ.get('EXPECTED_HISTORY_SHA256', '')
    archive_hash = os.environ.get('APPROVED_ARTIFACT_SHA256', '')
    validate_inputs(run_id, name, history, archive_hash)
    token = os.environ.pop('COT_SOURCE_READ_TOKEN', '')
    if not token:
        raise ValueError('Private Actions read credential has not been configured')
    run = api_json(f'{API}/runs/{run_id}', token)
    artifacts = []
    for page in range(1, 11):
        batch = api_json(f'{API}/runs/{run_id}/artifacts?per_page=100&page={page}', token)
        artifacts.extend(batch['artifacts'])
        if len(artifacts) >= batch['total_count']:
            break
    else:
        raise ValueError('Too many source artifacts')
    selected = select_artifact(run, artifacts, run_id, name, archive_hash)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / 'approved.zip'
        download_archive(selected['id'], token, archive)
        if sha256(archive.read_bytes()) != archive_hash:
            raise ValueError('Downloaded ZIP differs from approval')
        extract_verified_archive(archive, Path('site'), archive_hash, history)
    # Never print response bodies, payloads, signed URLs, or exception details.
    print('Selected artifact provenance, approved ZIP digest, and static site verified.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Approved artifact retrieval or verification failed; nothing was uploaded.') from None

