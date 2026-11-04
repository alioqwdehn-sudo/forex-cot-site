# COT Intelligence — Non-Commercial only

All seven markets use official CFTC **Legacy Futures Only**, dataset `6dca-aqww`, and only Non-Commercial long, short and spreading fields. All prior TFF and Disaggregated classifications have been removed from the app, data and calculations.

Net = Long − Short. Weekly change = current net − previous net. Six-report bias is Bullish for a positive first-to-last change, Bearish for negative, and neutral for flat or fewer than six observations. Spreading is shown separately and excluded from directional net. This is descriptive positioning analysis, not a validated price forecast.

`node cot-intelligence/update.mjs` downloads all seven official series and validates them before replacing any files. `node cot-intelligence/test.mjs` tests calculations and schema. `node cot-intelligence/build.mjs` writes the static site. GitHub Pages updates through the existing weekly workflow. TradingView supplies a separate price widget.
