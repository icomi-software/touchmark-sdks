# touchmark

Official TypeScript client for the [Touchmark API](https://api.touchmark.dev/docs): email validation and mailbox checks, sender readiness, IP lookup and phone number validation. ESM, typed, no runtime dependencies; Node 20+, edge runtimes, Deno and Bun.

```bash
npm install touchmark
```

```ts
import { Touchmark, TouchmarkError } from "touchmark"

const tm = new Touchmark({ apiKey: process.env.TOUCHMARK_API_KEY })

const email = await tm.email.validate({ email: "jane@acme.com" })
const ip = await tm.ip.lookup({ ip: "203.0.113.7" })
const phone = await tm.phone.validate({ phone: "020 7946 0000", country: "GB" })

const check = await tm.email.verify({ email: "jane@acme.com" })
const done = check.status === "done" ? check : await tm.email.waitForVerification(check.id!)
```

- Every call costs the credits of the API call it makes; see the [API reference](https://api.touchmark.dev/docs).
- Errors throw `TouchmarkError` with `status`, `code`, `detail`, `requestId` and `retryAfter`.
- Each charged call sends an `Idempotency-Key` (a random one, or yours: `tm.ip.lookup(body, { idempotencyKey })`), so the API charges it at most once.
- Network errors and `429`, `409 idempotency_key_in_use`, `500`, `502`, `503` and `504` answers are retried with the same key and body, at most twice; other errors are not.
- If you show IP country or network data to anyone, keep the credit "IP Geolocation by DB-IP" (https://db-ip.com) next to it.

Using the Touchmark API is subject to the [Terms of Service](https://touchmark.dev/legal/terms) and the [Acceptable Use Policy](https://touchmark.dev/legal/acceptable-use). The client sends requests only to the API base URL and includes no telemetry.

MIT licence. The licence covers the code only and grants no rights to the Touchmark name or logo.
