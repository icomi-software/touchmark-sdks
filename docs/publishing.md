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
   gh repo create icomi-software/touchmark-sdks --public --source=. --remote=origin
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
3. On https://www.npmjs.com/package/touchmark → Settings → Trusted publishing, add GitHub Actions with: organisation or user `icomi-software`, repository `touchmark-sdks`, workflow `release-npm.yml`, environment `npm`. Then, under "Publishing access", choose to require two-factor authentication and disallow tokens.

## Once: PyPI

1. Sign in at https://pypi.org (create an account if needed) and turn on two-factor authentication.
2. Account settings → Publishing → "Add a new pending publisher": PyPI project name `touchmark`, owner `icomi-software`, repository `touchmark-sdks`, workflow `release-pypi.yml`, environment `pypi`.

## Once: after the GitHub account rename (2026-10-10)

The account `marcin-marciszewski` is now `icomi-software`. GitHub redirects the old name, but trusted publishing checks the repository owner by name, so update both publishers before the next release:
1. npm: https://www.npmjs.com/package/touchmark → Settings → Trusted publishing → delete the `marcin-marciszewski` publisher (it cannot be edited) and add a GitHub Actions publisher: organisation or user `icomi-software`, repository `touchmark-sdks`, workflow `release-npm.yml`, environment `npm`.
2. PyPI: https://pypi.org/manage/project/touchmark/settings/publishing/ → remove the `marcin-marciszewski` publisher and add one for owner `icomi-software`, repository `touchmark-sdks`, workflow `release-pypi.yml`, environment `pypi`.

## Every release

1. Release TypeScript 0.2.0, Python 0.2.0 or Go v0.1.0 only after validation-api's Idempotency-Key support is deployed, or a retried POST could be charged twice. Check:
   ```bash
   curl -s https://api.touchmark.dev/v1/openapi.json | grep -c Idempotency-Key
   ```
   Expected: a number above 0. Then run `bash scripts/sync-openapi.sh && bash scripts/generate.sh`, review the diff, run every package's tests, commit, and only then push tags.
2. Bump the version: `typescript/package.json` (and `npm install` to update the lock file), `python/pyproject.toml` (and `uv lock` in `python/` to update its lock file; `__version__` reads it), and/or `userAgent` in `go/touchmark.go`. Commit and push.
3. Push the tag:
   ```bash
   git tag ts-v0.2.0 && git push origin ts-v0.2.0   # TypeScript
   git tag py-v0.2.0 && git push origin py-v0.2.0   # Python
   git tag go/v0.1.0 && git push origin go/v0.1.0   # Go
   ```
   A Go module has no registry: its tag is the release. Expected, a few minutes later: `GOPROXY=https://proxy.golang.org go list -m github.com/icomi-software/touchmark-sdks/go@v0.1.0` prints the version.
4. Approve the run in the environment if you added yourself as a reviewer. Expected: the workflow ends green, and `npm view touchmark version` or `pip index versions touchmark` shows the new version. npm shows a "Provenance" badge on releases published this way.

## After an API change

Run `scripts/sync-openapi.sh` only once the API change is deployed to production, because the script fetches production's document.

```bash
bash scripts/sync-openapi.sh   # downloads https://api.touchmark.dev/v1/openapi.json
bash scripts/generate.sh       # regenerates the TypeScript types, Python models and Go types
```

Review the diff, run the tests (`npm test` in `typescript/`, `uv run pytest` in `python/`, `go test ./...` in `go/`), and release a new version.

## Optional: a real call

```bash
read -rs TOUCHMARK_API_KEY && export TOUCHMARK_API_KEY
bash scripts/live-check.sh
```

Costs 2 credits: one email validation per SDK.
