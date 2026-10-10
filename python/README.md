# touchmark

Official Python client for the [Touchmark API](https://api.touchmark.dev/docs): email validation and mailbox checks, sender readiness, IP lookup and phone number validation. Synchronous and asynchronous clients on `httpx`, with typed models. Python 3.11+.

```bash
pip install touchmark
```

```python
from touchmark import Touchmark, TouchmarkError

with Touchmark() as tm:  # reads TOUCHMARK_API_KEY
    email = tm.email.validate(email="jane@acme.com")
    ip = tm.ip.lookup(ip="203.0.113.7")
    phone = tm.phone.validate(phone="020 7946 0000", country="GB")

    check = tm.email.verify(email="jane@acme.com")
    if check.status != "done":
        check = tm.email.wait_for_verification(str(check.id))
```

`AsyncTouchmark` has the same methods with `await` (and `async with`).

- Every call costs the credits of the API call it makes; see the [API reference](https://api.touchmark.dev/docs).
- Errors raise `TouchmarkError` with `status`, `code`, `detail`, `request_id` and `retry_after`.
- Each charged call sends an `Idempotency-Key` (a random one, or yours: `tm.ip.lookup(ip, idempotency_key=...)`), so the API charges it at most once.
- A key belongs to one request: reuse it only to retry that same call, with the same SDK. Another body or endpoint, or more than 10 replays, answers `422 idempotency_key_reused`.
- Network errors and `429`, `409 idempotency_key_in_use`, `500`, `502`, `503` and `504` answers are retried with the same key and body, at most twice; other errors are not.
- If you show IP country or network data to anyone, keep the credit "IP Geolocation by DB-IP" (https://db-ip.com) next to it.

Using the Touchmark API is subject to the [Terms of Service](https://touchmark.dev/legal/terms) and the [Acceptable Use Policy](https://touchmark.dev/legal/acceptable-use). The client sends requests only to the API base URL and includes no telemetry.

MIT licence. The licence covers the code only and grants no rights to the Touchmark name or logo. Dependencies: `httpx` (BSD-3-Clause), `attrs` (MIT), `python-dateutil` (Apache-2.0 or BSD-3-Clause).
