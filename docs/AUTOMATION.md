# Proposed unattended publisher: inactive until separate setup

The new workflow lives in `deploy/automation/automatic-pages.yml`, outside
Actions discovery. This draft activates nothing and creates no credentials or
deployments. The existing manual workflow remains the emergency fallback.
Automatic operation never reads `PAGES_PUBLISH_ENABLED`; no weekly user approval
or dispatch is needed after the one-time setup.

The source relay automatically supplies a numeric run ID. Public verification
requires a successful private main run of the fixed automatic source workflow,
own repository ID 1410262806, allowed schedule/dispatch event and exact artifact
origin/commit. It verifies GitHub's ZIP digest against downloaded bytes before
safe extraction. Only the exact 28-file static website can be uploaded; no
private checkout, raw snapshot, SQLite database, secret, executable private code
or backup is included. Existing ZIP/JSON traversal, duplicate, link, oversized
and inventory checks remain. All ten complete histories, pair aliases, counts,
weekly dates, growth and every previously published row are checked. Replay,
rollback and rewritten rows are rejected. Frontend asset fingerprints are fixed
to reviewed V4 code; new code needs a policy PR, data needs no weekly review.

## One-time setup after reviewing all three draft PRs

1. Keep the site public with Pages Source set to GitHub Actions. GitHub Free
   supports public Pages without publishing private source. No paid services or
   billing overages are needed; private source uses included Actions minutes.
2. Prefer a GitHub App installed **only** on private source with Actions **read**
   plus implicit Metadata read. Set public variable `COT_SOURCE_APP_ID` and
   `automatic-source` environment secret `COT_SOURCE_APP_PRIVATE_KEY`. The pinned
   App action mints/revokes short-lived tokens. A source-only fine-grained PAT in
   `COT_SOURCE_READ_TOKEN` is an alternative requiring expiry renewal. Neither
   requires Contents/Workflows/Admin permission.
3. Source uses a separate App installed only on this public site with Actions
   **write** for dispatch. Its ID/key live in source's `automatic-dispatch`
   variable/environment. Do not combine the Apps, which would unnecessarily
   grant source Actions write. The dispatch credential cannot push public code.
4. Restrict `automatic-source` and `github-pages` environments to main, with no
   required weekly reviewer/wait timer. Review changes to workflows/verifiers
   through protected main. Removing weekly environment approval replaces human
   artifact review with trust in source verification and authenticated provenance.
   Anyone controlling either main or App keys is inside that trust boundary.
5. Permit the receipt job's public `GITHUB_TOKEN` Contents write on the
   `automatic-published` data-only branch; keep main protected. The separate
   deploy job has only Pages write + id-token write and no source credential.
6. In a separate approved activation change copy the template into
   `.github/workflows/automatic-pages.yml`, then set `COT_AUTOMATION_READY=true`
   once. Activate matching source/mirror templates last. Merely merging this
   draft PR leaves the template inactive. No settings are changed by these PRs.
7. Enable owner Actions failure notifications and check the first verified
   artifact, successful deployment and durable receipt. Source `AUTOMATION.md`
   documents complete schedules, validation, history persistence and setup.

Actions read can access all private source artifacts/logs, not just the selected
artifact; GitHub provides no per-artifact credential scope. The downloader binds
credentials to the fixed API and never forwards them to signed storage redirects.
It executes no artifact content. Fixed assets and typed JSON reduce accidental
exposure; compromised trusted code can still encode information inside data.
No secrets or private payloads should be logged in source Actions.

## Failure and rollback

Manual and automatic publication share `approved-pages-artifact` concurrency
without cancellation. Only complete verified artifacts deploy. Successful receipts
skip repeat releases. Source retries through Tuesday and relays daily. Failures
produce safe Actions errors without private data or signed URLs. Artifacts expire;
private history and public 28-file receipts are durable Git data.

Pages deployment and receipt persistence are separate operations. A failure after
deploy but before recording the receipt may replay the identical generation once
to reconcile state; history is never appended twice and no partial site is sent.
Expired/unverifiable artifacts never bypass policy. Live credentials/deployments
are intentionally untested until separate owner activation.

For rollback, pause source/site using `COT_AUTOMATION_READY=false`, cancel pending
automatic releases, then use the unchanged manual workflow's owner approval and
reviewed ZIP digest. Default manual policy permits the original seed. Another
approved generation requires a reviewed `MANUAL_APPROVED_HISTORY` policy change,
independently of the fixed automatic seed anchor. Never reset/delete verified
private history or fabricate a successful receipt. Keep automation paused until
receipts/forward recovery are reconciled; revoke compromised keys before resuming.

[GitHub authentication](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)
and [workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
describe token permissions and schedule/dispatch limitations.
