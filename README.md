# Forex COT Dashboard V4 — public publishing repository

This repository prepares manual GitHub Pages delivery of a separately reviewed
static artifact from `alioqwdehn-sudo/forex-cot-platform`. It contains publishing
automation, an independently implemented public verifier, and synthetic tests.
It does not contain the private application or its raw history.

**Prepared only: do not merge or deploy until reviewed.** Pages Source is already
GitHub Actions. No workflow dispatch, secret creation, environment setup, or
publication is part of this change. Merging does not publish a site.

See [deployment and security instructions](docs/DEPLOYMENT.md).

Run the offline security tests with Python 3.11 or later:

```text
python -m unittest discover -s tests -v
```

The test fixtures are synthetic, created temporarily, and never published.
