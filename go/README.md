# touchmark (Go)

Official Go client for the [Touchmark API](https://api.touchmark.dev/docs): email validation and mailbox checks, sender readiness, IP lookup and phone number validation. Go 1.20+, standard library only.

```bash
go get github.com/icomi-software/touchmark-sdks/go
```

```go
import touchmark "github.com/icomi-software/touchmark-sdks/go"

tm, err := touchmark.New(touchmark.Options{}) // reads TOUCHMARK_API_KEY

email, err := tm.Email.Validate(ctx, touchmark.ValidateRequest{Email: "jane@acme.com"})
ip, err := tm.IP.Lookup(ctx, touchmark.LookupRequest{IP: "203.0.113.7"})
phone, err := tm.Phone.Validate(ctx, touchmark.PhoneValidateRequest{Phone: "020 7946 0000", Country: touchmark.String("GB")})

check, err := tm.Email.Verify(ctx, touchmark.ValidateRequest{Email: "jane@acme.com"})
if err == nil && check.Status != "done" {
	check, err = tm.Email.WaitForVerification(ctx, *check.ID, time.Minute)
}
```

- Every call costs the credits of the API call it makes; see the [API reference](https://api.touchmark.dev/docs).
- Errors are `*touchmark.Error` with `Status`, `Code`, `Detail`, `RequestID` and `RetryAfter`.
- Each charged call sends an `Idempotency-Key` (a random one, or yours: `touchmark.WithIdempotencyKey(key)`), so the API charges it at most once.
- A key belongs to one request: reuse it only to retry that same call, with the same SDK. Another body or endpoint, or more than 10 replays, answers `422 idempotency_key_reused`.
- Network errors and `429`, `409 idempotency_key_in_use`, `500`, `502`, `503` and `504` answers are retried with the same key and body, at most twice; other errors are not. `Options.MaxRetries` changes the count, and a negative value turns retries off.
- Redirects are not followed, so your key is never sent to another origin.
- If you show IP country or network data to anyone, keep the credit "IP Geolocation by DB-IP" (https://db-ip.com) next to it.

Using the Touchmark API is subject to the [Terms of Service](https://touchmark.dev/legal/terms) and the [Acceptable Use Policy](https://touchmark.dev/legal/acceptable-use). The client sends requests only to the API base URL and includes no telemetry.

MIT licence. The licence covers the code only and grants no rights to the Touchmark name or logo.
