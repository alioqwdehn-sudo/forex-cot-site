# GitHub Free public polling — inactive proposal

All new workflows remain templates under deploy/automation. No schedules,
secrets, settings, readiness flags or deployments are changed. Keep
COT_AUTOMATION_READY=false until separate owner authorization.

## Public security boundary

The site polls private-source successful Actions runs; it does NOT accept an
untrusted source-supplied run ID for production. The existing source-read App
must be source-only Actions READ + Metadata read. Public repository variable
COT_SOURCE_APP_ID selects it; its private key stays exclusively in the main-only
automatic-source environment as COT_SOURCE_APP_PRIVATE_KEY. Do not move that
key into private source or a repository-level public secret. Neither repository
needs the source-dispatch App; this proposal deletes no installation/secret.

GitHub Free supports public environments/branch protection/Pages. It does NOT
support enforced private branch protection or private environment restrictions.
Repository-level secrets are available, but workflow writers can extract them;
they do not replace a main-only environment boundary. Source main is therefore
not trusted merely because its name is main. Official documentation:
[environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments),
[branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches),
[secrets](https://docs.github.com/en/actions/reference/security/secure-use).

scripts/source_policy.py approves exact SOURCE commit SHAs, not branches/tags or
inputs. The shipped approval set is EMPTY deliberately. After separately copying
source templates during owner activation, record its final main SHA through a
protected public policy PR; add the preflight SHA before testing and the final
production SHA before readiness. No weekly review is needed because source
history changes happen on a separate data-only branch. Any code change needs a
new SHA policy approval. Pins are not proof a reviewed dependency/runner is safe.

Ten pinned original-history fingerprints are computed from the approved
910-record seed's public API rows, with sorted keys and lossless IEEE-754 numeric
encoding (JSON integers/floats compare identically). They prevent original-row
rewrites even before first receipt. No raw seed, SQLite, archive or private code
is committed publicly. Fixed V4 assets and exactly 28 files remain mandatory.

The verifier binds source repository ID, approved SHA, workflow path, main,
schedule/dispatch event, success, run ID, artifact name, API digest and downloaded
ZIP digest. Full contracts, ten currency MAX series, pair aliases, dates, counts,
immutable previous rows and lineage growth are checked. Production requires
mode=production; preflight origin/name/mode cannot authorize production or receipts.

New rows are checked against independently downloaded official CFTC TFF
Futures-Only weekly CSV. Missed public weeks additionally use the fixed official
annual futures-only text ZIP, read in memory with size/schema/member limits.
Every new row must equal the official API projection; percentages, deltas and
open-interest anomaly checks also apply. Archive lag, source corrections, HTTP
errors or changed ZIP schema stop publication, never cause unverified fallback.
See [official archives](https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm).

## Jobs and preflight

Production automatic-pages.yml polls hourly at :11 UTC Friday-Tuesday and
Wednesday/Thursday 09:11 UTC for recovery, plus optional emergency dispatch.
At most 500 successful source runs are scanned to find the newest approved,
unique, unexpired artifact. No-op source runs do not hide pending releases.
Already-receipted releases do not deploy again. Production requires readiness.

Retrieval/verification job: own token Contents read; source App token Actions
read. Separate deploy job: Pages write + ID-token write, no source credential.
Separate receipt job: Contents write, only after deployment success. Private
Contents, Workflows, Administration, or Actions write are never granted.

automatic-preflight.yml is dispatch-only and has only a Contents-read job. It
accepts a SOURCE preflight run ID, repeats all independent checks, emits
publish=false unconditionally and has NO upload-pages/deploy/receipt jobs.
It can run while readiness is false. Source preflight validates a disposable
history copy and uploads only a distinctly named 28-file preview; no push.
No new/pending report means no preview artifact, not permission to fabricate one.

## Exact future owner order

1. Review/merge inactive code and pass tests while flags remain false. Preserve
   merged mirror freshness fix and unchanged manual fallback.
2. Confirm App/key location, source-only read installation, public main protection,
   main-only automatic-source/github-pages, no weekly reviewers/wait timers and
   GitHub Actions Pages source. Do not disable manual owner approval policy.
3. Activate only dispatch-only source/public preflight in a separately approved
   change; approve final SOURCE SHA in this public policy. Run source preflight,
   then public preflight with its run ID. Confirm no history push, Pages artifact,
   deployment or receipt. Test App authentication without exposing keys/logs.
4. After separate production approval copy public polling/source weekly templates;
   replace mirror legacy writer in one change, never keep both writers. Do not
   activate any old dispatch relay. Approve final source activation SHA publicly.
5. Set site readiness true first and source true last. Observe first append,
   artifact, independent official verification, complete deployment and receipt.
6. Enable owner failure notifications, monitor best-effort/inactivity schedules,
   private included minutes/storage and expired-artifact recovery. No paid overages.

Public standard runners/Pages are free; private source uses shared Free quotas
(2,000 minutes/month, 500 MB artifact storage). Source now validates twice for
permission separation, increasing minutes. See [billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## Recovery, manual fallback and unavoidable risks

History-push/upload failures recover without double appends. Pages success before
receipt failure can replay the identical complete release. Leases/receipt checks
prevent stale/duplicate history; exactly-once remote deployment is not guaranteed.
Manual and automatic publication share one concurrency lock. Pending jobs may be
replaced by newer jobs; schedules are not a delivery SLA.

Emergency owner action: readiness false in source/site AND cancel pending/running
automatic jobs; changing a flag does not recall a running release. Use unchanged
manual pages-approved-artifact.yml with reviewed digest and owner gates. Default
manual history remains the original seed; another generation requires a reviewed
MANUAL_APPROVED_HISTORY policy change. Never delete private verified history or
forge a receipt. Reconcile receipts/forward recovery before resuming.

Anyone controlling public policy/key/account remains trusted. Source-read App
can read all private Actions logs/artifacts, not only a selected artifact. Never
upload/log private source, credentials, SQLite or raw history. API authentication
is never forwarded to signed storage URLs. Public jobs check out only public
scripts and execute no private/artifact code. Unprotected private writers can
delete history, change workflows and steal private code; exact public SHA,
baseline and official checks reject resulting unreviewed publication but cannot
restore GitHub-enforced private protection. Restrict writers/integrations, secure
owner MFA and keep offline backups. No weekly human approval is introduced.
