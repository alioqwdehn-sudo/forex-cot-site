"""Future post-deploy durable public receipt: exactly the verified site files."""
import base64
import os
from pathlib import Path
import subprocess
import tempfile

from automatic_publication import STATE_BRANCH, read_json, verify_contract
from verify_static_site import FILES, verify_site


def git(*args, env=None):
    return subprocess.run(['git',*args],env=env,check=True,capture_output=True).stdout


def record(site,previous,token):
    if previous and (len(previous)!=40 or any(c not in '0123456789abcdef' for c in previous)): raise ValueError('Invalid state lease')
    manifest=read_json(Path(site)/'data/generation.json')
    if manifest.get('release',{}).get('mode')!='production':
        raise ValueError('Preflight/legacy artifacts cannot write an automatic receipt')
    verify_site(site,manifest['history_sha256'],automatic=True)
    verify_contract(site,manifest)
    with tempfile.TemporaryDirectory() as tmp:
        env=dict(os.environ,GIT_INDEX_FILE=str(Path(tmp)/'index'),GIT_CONFIG_COUNT='1',
            GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
            GIT_CONFIG_VALUE_0='AUTHORIZATION: basic '+base64.b64encode(('x-access-token:'+token).encode()).decode(),
            GIT_AUTHOR_NAME='Verified Pages bot',GIT_AUTHOR_EMAIL='github-actions[bot]@users.noreply.github.com',
            GIT_COMMITTER_NAME='Verified Pages bot',GIT_COMMITTER_EMAIL='github-actions[bot]@users.noreply.github.com')
        if previous: git('fetch','--no-tags','origin',f'refs/heads/{STATE_BRANCH}',env=env)
        git('read-tree','--empty',env=env)
        for name in sorted(FILES):
            blob=git('hash-object','-w',str(Path(site)/name),env=env).decode().strip()
            git('update-index','--add','--cacheinfo',f'100644,{blob},{name}',env=env)
        tree=git('write-tree',env=env).decode().strip()
        parents=['-p',previous] if previous else []
        commit=git('commit-tree',tree,*parents,'-m','Record successfully deployed verified static generation',env=env).decode().strip()
        git('push',f'--force-with-lease=refs/heads/{STATE_BRANCH}:{previous}','origin',f'{commit}:refs/heads/{STATE_BRANCH}',env=env)


if __name__=='__main__':
    try: record('site',os.environ.get('PREVIOUS_STATE_HEAD',''),os.environ.pop('GH_TOKEN'))
    except Exception: raise SystemExit('Post-deploy receipt failed. Site may already be live; retry the same release to reconcile safely. Do not rewrite source history.') from None
