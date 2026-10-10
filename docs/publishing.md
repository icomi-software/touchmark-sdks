# Publishing the SDKs

Only the owner publishes. Agents prepare releases but never push, tag or publish.

## Before the first release

The clients are generated from `openapi/openapi.json`. Before you publish, check that it equals the document production serves:

```bash
bash scripts/sync-openapi.sh && git diff --exit-code openapi/openapi.json
```

Expected: no diff. A diff means production serves a different document: deploy `validation-api` first, or regenerate (`bash scripts/generate.sh`), review and commit, then check again.

## Once: the public repository

1. Create the empty public repository and push this folder (from this folder):
   ```bash
   git status --short   # prints nothing: the folder's history is already committed
   gh repo create marcin-marciszewski/touchmark-sdks --public --source=. --remote=origin
   git push -u origin main
   ```
   Expected: the CI workflow runs on `main` and ends green.
2. In the repository's Settings → Environments, create two environments, `npm` and `pypi`. Optional but recommended: under each, add yourself as a required reviewer, so no release runs without your click.

## Once: npm

1. Sign in at https://www.npmjs.com (create an account if needed) and turn on two-factor authentication.
2. npm lets you add a trusted publisher only to a package that already exists, so publish `0.1.0` once by hand, from your laptop:
   ```bash
   cd typescript
   npm ci && npm test
   npm login
   npm publish --access public
   ```
   Expected: `npm view touchmark version` prints `0.1.0`.
3. On https://www.npmjs.com/package/touchmark → Settings → Trusted publishing, add GitHub Actions with: organisation or user `marcin-marciszewski`, repository `touchmark-sdks`, workflow `release-npm.yml`, environment `npm`. Then, under "Publishing access", choose to require two-factor authentication and disallow tokens.

## Once: PyPI

1. Sign in at https://pypi.org (create an account if needed) and turn on two-factor authentication.
2. Account settings → Publishing → "Add a new pending publisher": PyPI project name `touchmark`, owner `marcin-marciszewski`, repository `touchmark-sdks`, workflow `release-pypi.yml`, environment `pypi`.

## Every release

1. Bump the version: `typescript/package.json` (and `npm install` to update the lock file), `python/pyproject.toml` (and `uv lock` in `python/` to update its lock file; `__version__` reads it), and/or `userAgent` in `go/touchmark.go`. Commit and push.
2. Push the tag:
   ```bash
   git tag ts-v0.1.1 && git push origin ts-v0.1.1   # TypeScript
   git tag py-v0.1.0 && git push origin py-v0.1.0   # Python (its first release goes this way)
   git tag go/v0.1.0 && git push origin go/v0.1.0   # Go
   ```
   A Go module has no registry: its tag is the release. Expected, a few minutes later: `GOPROXY=https://proxy.golang.org go list -m github.com/marcin-marciszewski/touchmark-sdks/go@v0.1.0` prints the version.
   Never push `ts-v0.1.0`: you published 0.1.0 to npm by hand, so its release run would fail at `npm publish` (the version exists). The first TypeScript tag is `ts-v0.1.1`.
3. Approve the run in the environment if you added yourself as a reviewer. Expected: the workflow ends green, and `npm view touchmark version` or `pip index versions touchmark` shows the new version. npm shows a "Provenance" badge on releases published this way.

## After an API change

Run `scripts/sync-openapi.sh` only once the API change is deployed to production, because the script fetches production's document.

```bash
bash scripts/sync-openapi.sh   # downloads https://api.touchmark.dev/v1/openapi.json
bash scripts/generate.sh       # regenerates the TypeScript types and Python models
```

Review the diff, run the tests (`npm test` in `typescript/`, `uv run pytest` in `python/`), and release a new version.

## Optional: a real call

```bash
read -rs TOUCHMARK_API_KEY && export TOUCHMARK_API_KEY
bash scripts/live-check.sh
```

Costs 2 credits: one email validation per SDK.
