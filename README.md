# Touchmark SDKs

Official client libraries for the [Touchmark API](https://api.touchmark.dev/docs): email validation and mailbox checks, sender readiness, IP lookup and phone number validation.

| Language | Package | Folder |
| --- | --- | --- |
| TypeScript / JavaScript | [`touchmark`](https://www.npmjs.com/package/touchmark) on npm | [`typescript/`](typescript/) |
| Python | [`touchmark`](https://pypi.org/project/touchmark/) on PyPI | [`python/`](python/) |
| Go | `github.com/marcin-marciszewski/touchmark-sdks/go` | [`go/`](go/) |

## TypeScript

```bash
npm install touchmark
```

```ts
import { Touchmark } from "touchmark"

const tm = new Touchmark({ apiKey: process.env.TOUCHMARK_API_KEY })
const answer = await tm.email.validate({ email: "jane@acme.com" })
console.log(answer.result)
```

## Python

```bash
pip install touchmark
```

```python
from touchmark import Touchmark

tm = Touchmark()  # reads TOUCHMARK_API_KEY
answer = tm.email.validate(email="jane@acme.com")
print(answer.result)
```

`AsyncTouchmark` offers the same methods with `await`.

## Go

```bash
go get github.com/marcin-marciszewski/touchmark-sdks/go
```

```go
tm, err := touchmark.New(touchmark.Options{}) // reads TOUCHMARK_API_KEY
if err != nil {
	log.Fatal(err)
}
answer, err := tm.Email.Validate(ctx, touchmark.ValidateRequest{Email: "jane@acme.com"})
if err != nil {
	log.Fatal(err)
}
fmt.Println(answer.Result)
```

## Behaviour

- Every call costs the credits of the API call it makes; see the API reference.
- Errors raise `TouchmarkError` with `status`, `code`, `detail`, `request_id` and `retry_after` (`*touchmark.Error` in Go).
- Each charged call sends an `Idempotency-Key`: a random one, or one you pass. The API charges a call at most once per key and body for 24 hours.
- A key belongs to one request: reuse it only to retry that same call, with the same SDK. Another body or endpoint, or more than 10 replays, answers `422 idempotency_key_reused`.
- Network errors and `429`, `409 idempotency_key_in_use`, `500`, `502`, `503` and `504` answers are retried with the same key and body, at most twice, after `Retry-After` or 1 then 2 seconds (never more than 30). Other errors are not retried.
- `email.verify` returns at once; `email.wait_for_verification` (`waitForVerification` in TypeScript) waits for a mailbox check to finish.

## Terms and privacy

Using the Touchmark API is subject to the [Terms of Service](https://touchmark.dev/legal/terms) and the [Acceptable Use Policy](https://touchmark.dev/legal/acceptable-use). The SDKs collect nothing: they send your requests only to the API base URL you configure (`https://api.touchmark.dev` by default) and include no telemetry.

## Licence

MIT; see [LICENSE](LICENSE). The licence covers the code only and grants no rights to the Touchmark name or logo. The MIT notices of the two code generators are kept in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) as a courtesy. The Python package depends on `httpx` (BSD-3-Clause), `attrs` (MIT) and `python-dateutil` (Apache-2.0 or BSD-3-Clause), installed from PyPI. The Go module uses the standard library only.

## Keeping in step with the API

`bash scripts/sync-openapi.sh` downloads the public API document into `openapi/openapi.json`; `bash scripts/generate.sh` regenerates the three clients from it. CI fails if the generated code does not match the document.
