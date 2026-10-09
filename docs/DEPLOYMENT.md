# Reviewed static artifact publication — single owner

## Status and trust boundary

The public workflow is manual (`workflow_dispatch`) only. There is no push,
pull-request, scheduled, or private-workflow-completion publication trigger.
It runs only on this repository's `main` branch, with both `publish=true` and
the repository variable `PAGES_PUBLISH_ENABLED=true`. Missing or false gates
skip both jobs, including the public Pages artifact upload. Do not enable the
variable, create credentials, merge, or dispatch as part of reviewing this PR.

Pages Source has already been configured as GitHub Actions; no configure-pages
action is needed to change or enable it. Official `actions/upload-pages-artifact`
and `actions/deploy-pages` actions handle publication; all actions are pinned to
full commit SHAs. Python standard library code handles strict download and ZIP
verification, because an archive digest mismatch must fail, not merely warn.

The publishing repository never checks out the private repository and never
executes artifact content. The source token is available to the retrieval step
only; checkout does not persist credentials. The downloader authenticates only
requests to the fixed private repository's Actions API. GitHub's signed ZIP
redirect is fetched without an Authorization header. Errors never print API
response bodies, exception details, signed URLs, or artifact contents. No caches
or diagnostic artifact uploads exist. The downloaded ZIP is temporary. Only the
verified `site` directory is submitted to Pages, with one-day artifact retention.
The deploy job uses a separate hosted runner and has no source token.

## Review of the private template and verifier

Reviewed `deploy/pages-approved-artifact.yml` and `verify_static_site.py` at private
source commit `2240f6369bdd0ede0a08d0212dc396bf62bf6c71`. Template blob:
`f229518e7f3673dde1ab2a3a8fb50ca091017de3`; verifier blob:
`a8c12a7c93478ac5499835c1c1b560130abbfb0b`.

The template already separates retrieval and deployment, accepts run/name/history,
and uses official Pages actions. Its verifier checks the exact static file
inventory, SHA-256 for data/assets, no symlinks, and at least 910 records. The
history hash is a declaration in the generation manifest: without raw history it
cannot be recalculated from the exported responses. Manifest checksums detect
corruption but cannot authenticate an attacker-replaced file plus manifest.

This PR independently implements the same public file contract instead of
copying private application code. It also fixes the source repository, requires
successful manual `static-pages.yml` runs from its own `main` branch, rejects
forks, matches the artifact's run and source commit, requires an owner-reviewed
ZIP hash equal to GitHub's artifact digest, and hashes the downloaded ZIP
before extraction. It rejects duplicate ZIP/JSON entries, traversal, special
files, links, unexpected directories, missing files, and oversized archives.
Missing digests fail closed. Builds using incompatible legacy artifact formats
must be rebuilt and reviewed; never bypass digest checks.

The expected approved history is fixed in the public verification policy:

```text
068962973edc3e7586316cea3c54871efdb12b8441a9790309a9dbdf1318123b
```

A different history requires a new reviewed PR changing that policy. At least
910 records are required, preserving the private verifier's minimum. That field
is metadata; the full-history and CFTC correctness review remains with the private
build review. No real build run or ZIP digest has been approved by this PR.

## Single-owner administrator setup after explicit authorization

The repository owner is the only administrator and maintainer. No second-person
approval is required. Without an independent reviewer, the owner is responsible
for reviewing the exact artifact contents, source run provenance, history hash,
and independently computed ZIP hash before enabling publication and dispatching.
Environment branch restrictions and automated verification enforce the deployment
policy; they do not provide a second human review.

1. Review and merge this PR when authorized. Use PRs for the owner's review and
   restrict workflow/script changes to the owner. Do not configure branch rules
   that require another person's PR approval in this single-owner model. Write access can
   change workflow code; neither hash checks nor masked secrets protect against
   a malicious trusted workflow author. Avoid repository-wide private tokens.
2. Create the public repository's `source-artifact` environment. Allow only the
   `main` deployment branch where supported: choose **Selected branches and tags**,
   add a **Branch** rule with the exact pattern `main`, and add no tag rules.
   Leave **Required reviewers** empty and **Prevent self-review** disabled; remove
   any previously configured reviewer requirement. This environment scopes the
   private read token to artifact retrieval. The owner must review the exact
   run/name/history/ZIP hash tuple and public disclosure before dispatch.
3. Keep `github-pages` with the same `main`-only branch rule and no tag rules where
   supported. Leave **Required reviewers** empty and **Prevent self-review**
   disabled; remove any previously configured reviewer requirement. The deploy
   job proceeds after successful verification without a human approval prompt.
   A workflow reference alone does not configure protection: GitHub can create
   an unrestricted environment on first use, so configure both before dispatch.
   If environment branch restrictions are unavailable, the workflow's explicit
   `github.ref == 'refs/heads/main'` condition remains mandatory in both jobs.
4. An authorized administrator must manually create a short-lived fine-grained
   PAT restricted to **only** `alioqwdehn-sudo/forex-cot-platform`, with **Actions:
   read** and automatically required metadata read. No contents write, source
   checkout, administration, or classic broad `repo` scope is needed. Store it
   only as the `source-artifact` environment secret `COT_SOURCE_READ_TOKEN`.
   Honor any organization approval/SSO requirements. Rotate/revoke it after use
   when possible. The public repository's `GITHUB_TOKEN` cannot read artifacts
   from the private source repository by itself.
5. Confirm Actions policy permits the pinned official actions, Pages remains
   set to GitHub Actions, and both environments have the supported branch
   restrictions with no required reviewers. Only after the owner's content/hash
   review and explicit publication authorization set the **repository** variable
   `PAGES_PUBLISH_ENABLED` to `true`. Environment-only variables are too late for
   the job condition. Keep it unset/false until then; reset it after publication
   to require explicit re-enabling for the next release.

No secrets, variables, environments, or repository settings are created by the
workflow preparation. An authorized dispatch user needs write access; environment
configuration requires repository administrator access. GitHub App/connector
permission to edit workflow files is separate from displayed repository push
permission, and may require Workflows write permission.

## Review a source artifact before a future dispatch

Use a successful manually triggered `.github/workflows/static-pages.yml` build
on private `main`, with its private publishing option left false. The artifact
must be the exact `static-site-preview-<40-character source commit SHA>` generated
by that run. Never select the latest run, a wildcard, an artifact from a PR/fork,
or the Pages packaging artifact.

The owner must, in an authorized private review session, download the selected Actions artifact
ZIP, review the extracted static frontend and exported response contents for
secrets/private data, and verify it with the private verifier and this public
verifier. Record the immutable artifact ID, run ID, source commit, exact name,
GitHub `digest` (`sha256:...`), independently computed ZIP SHA-256, and history
SHA-256. For example, use `Get-FileHash -Algorithm SHA256 approved.zip` or
`sha256sum approved.zip`. The approved ZIP hash must equal the artifact's API
digest. Hash the exact downloaded ZIP, not a re-zipped folder, tar, or manifest.
API metadata alone is not content review. Keep this approval record private.

The exact allowlist has 28 files:

* `index.html`, `data-source.js`, empty `.nojekyll`;
* `data/generation.json`;
* `data/currencies.json`, `data/pairs.json`, `data/health.json`, `data/ready.json`;
* `data/cot/<currency>.json` for AUD, GBP, CAD, EUR, JPY, NZD, CHF, BRL, MXN, ZAR;
* `data/pair/<pair>.json` for EUR-USD, GBP-USD, AUD-USD, NZD-USD, USD-CAD,
  USD-CHF, USD-JPY, USD-MXN, USD-BRL, USD-ZAR.

All other files are rejected before extraction: SQLite databases, WAL/SHM,
backups, raw `history/records-*.json`, `.env`, source Python, and nested archives
are not allowed. A 100 MiB limit applies to both ZIP and expanded files. The
allowlist cannot determine whether a permitted HTML/JS/JSON file contains private
text: private content review and the approved ZIP checksum provide that assurance.
Exported dashboard history becomes public; raw 46-column snapshots stay private.
The public Pages artifact becomes accessible before the deploy job completes,
so the owner's review before dispatch must cover public artifact disclosure as
well as website publication. There is no intervening environment reviewer gate.

When separately authorized, dispatch **Publish approved static artifact (manual)**
on `main` and explicitly enter all four strings: `source_run_id`, `artifact_name`,
`expected_history_sha256`, and `approved_artifact_sha256` (64 lowercase hex digits,
without `sha256:`). The owner must check that tuple before dispatch and set
`publish=true` only for an explicitly authorized release. Neither environment
requires reviewers; there is no second approval prompt between dispatch, upload,
and deployment. Any validation failure prevents
the upload and downstream deployment. Input strings are passed through environment
variables, never interpolated into shell commands.

## GitHub Free and permissions

GitHub Pages is available for **public** repositories on GitHub Free. Pages
hosting from a **private** repository needs an eligible paid plan; keep the
private source private. Environments, environment secrets, and deployment branch
restrictions are available on the public publishing repository with GitHub Free.
This model uses both environments with no required reviewers or self-review
prevention, so a single owner can manually release after reviewing the artifact
and hashes. It needs no second administrator or paid approval feature. Environment
setup remains in the public repository; the source stays private.

Standard hosted runner usage for this public repository is free. Private source
build minutes and artifact storage remain subject to the source owner's quota;
expired/deleted artifacts, missing API digests, denied Actions access, or exhausted
private quotas require a new reviewed build or administrator resolution. This PR
does not inspect billing, enable paid services, or guarantee an account quota.

References:

* [Official Pages custom workflows and availability](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
* [Environment protections and plan availability](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
* [Artifact API and Actions read token permissions](https://docs.github.com/en/rest/actions/artifacts#download-an-artifact)
* [Actions billing and private quotas](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

## Validation and rollback

Run `python -m unittest discover -s tests -v` locally. Tests use synthetic content
only and exercise complete inventories, content corruption, a rewritten manifest
against an approved ZIP, wrong history, insufficient counts, private extra files,
traversal, duplicate entries, links, size limits, untrusted run provenance, expired
or ambiguous artifacts, invalid digest approval, and input injection. The separate
`validate-publication.yml` workflow runs YAML parsing, Python compilation, and these
tests on pull requests or manual dispatch. It has only contents read permission,
no environments, no secrets, no artifact uploads, and no publication steps. It
never retrieves a real private artifact.

A future rollback is a separately approved manual dispatch of an old reviewed,
unexpired artifact with its original approval tuple. If it expired, rebuild the
reviewed source commit and have the owner review the new run/ZIP digest. The current
policy only accepts the stated history checksum; rollback to a different history
requires a policy PR. Deploy the frontend and data together and reload browsers.
Do not change private history or SQLite to roll back the public site.
