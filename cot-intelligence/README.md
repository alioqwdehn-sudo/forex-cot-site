# COT Intelligence

Self-contained public website for EUR/USD, GBP/USD, Gold, DXY, ES, NQ and Silver. This is the independently built COT Intelligence app, not a private forex-cot-platform artifact. Existing publishing scripts and workflows are preserved.

Source: `source/page.html`, `source/engine.mjs`, `markets.json`, official CFTC seed reports in `data/`. No secrets or private account information are included. TradingView supplies price widgets and symbol SVGs embedded in the page; CFTC supplies positioning.

Build: `node cot-intelligence/build.mjs`.
Update official data: `node cot-intelligence/update.mjs` then build. Node 22 required; no packages needed.

GitHub Actions publishes on main-source changes, and refreshes all seven official datasets on Saturday at 00:45 Baghdad time (Friday 21:45 UTC), with a Saturday 10:45 Baghdad retry. Schedules can be delayed by GitHub. Upstream failures stop publication and retain the prior deployed site. Source credentials and private platform artifacts are never used by this workflow. GitHub Pages must use the GitHub Actions source, already documented by this repository.

Report dates are positioning dates, not publication dates. COT is delayed weekly data. Bias is a descriptive six-report positioning rule, not a validated price forecast. Metals use Managed Money and Other Reportables, not TFF Asset Managers.
