"""The Touchmark API client.

Models come from the API's OpenAPI document (touchmark/_gen, generated); the
requests, errors and retries are written here, once for the synchronous and
once for the asynchronous client.
"""

from __future__ import annotations

import functools
import json
import math
import os
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

import anyio
import httpx

from ._gen.models import (
    AccountResponse,
    BatchLookupResponse,
    BatchValidateResponse,
    LookupResponse,
    PhoneBatchValidateResponse,
    PhoneValidateResponse,
    SenderReadinessResponse,
    ValidateResponse,
    VerifyResponse,
)

DEFAULT_BASE_URL = "https://api.touchmark.dev"
# Retries of network errors and of 429, 409 in-use and 5xx answers. Charged calls
# carry an Idempotency-Key, so a retry is charged at most once.
DEFAULT_MAX_RETRIES = 2
# The API's longest long poll for a mailbox check.
MAX_WAIT_SECONDS = 10
MAX_RETRY_DELAY_SECONDS = 30.0
DEFAULT_TIMEOUT_SECONDS = 30.0

R = TypeVar("R")


class TouchmarkError(Exception):
    """Any answer that is not 2xx, read from the API's problem document."""

    def __init__(
        self,
        *,
        status: int,
        code: str,
        detail: str | None,
        request_id: str | None,
        retry_after: float | None,
    ) -> None:
        super().__init__(f"{code}: {detail or f'HTTP {status}'}")
        self.status = status
        self.code = code
        self.detail = detail
        self.request_id = request_id
        self.retry_after = retry_after

    def __reduce__(self) -> tuple[Any, tuple[()]]:
        # The keyword-only __init__ would otherwise break pickling (multiprocessing).
        rebuild = functools.partial(
            type(self),
            status=self.status,
            code=self.code,
            detail=self.detail,
            request_id=self.request_id,
            retry_after=self.retry_after,
        )
        return rebuild, ()


@dataclass(frozen=True)
class _Call(Generic[R]):
    method: str
    path: str
    parse: Callable[[Mapping[str, Any]], R]
    body: Mapping[str, Any] | None = None
    params: Mapping[str, int] = field(default_factory=dict)


def _api_key(api_key: str | None) -> str:
    key = api_key or os.environ.get("TOUCHMARK_API_KEY")
    if not key:
        raise ValueError(
            "Touchmark: pass api_key or set the TOUCHMARK_API_KEY environment variable."
        )
    return key


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def _error(response: httpx.Response) -> TouchmarkError:
    try:
        problem = response.json()
    except ValueError:
        problem = {}  # not a problem document (a proxy's error page, for example)
    if not isinstance(problem, dict):
        problem = {}
    code = problem.get("code")
    detail = problem.get("detail")
    retry_after: float | None = None
    if (value := response.headers.get("retry-after")) is not None:
        try:
            seconds = float(value)
        except ValueError:
            seconds = math.nan
        # NaN, infinity or a negative value counts as no header.
        retry_after = seconds if math.isfinite(seconds) and seconds >= 0 else None
    return TouchmarkError(
        status=response.status_code,
        code=code if isinstance(code, str) else f"http_{response.status_code}",
        detail=detail if isinstance(detail, str) else None,
        request_id=response.headers.get("x-request-id"),
        retry_after=retry_after,
    )


def _retryable(error: TouchmarkError) -> bool:
    return error.status in (429, 500, 502, 503, 504) or (
        error.status == 409 and error.code == "idempotency_key_in_use"
    )


def _request(
    headers: Mapping[str, str], call: _Call[Any], idempotency_key: str | None
) -> tuple[bytes | None, dict[str, str]]:
    """The body and headers, the same on every retry.

    Every POST is charged, so it carries an Idempotency-Key: the API charges
    it at most once per key and body.
    """
    if call.body is None:
        return None, dict(headers)
    content = json.dumps(call.body, separators=(",", ":")).encode()
    return content, {
        **headers,
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key or str(uuid.uuid4()),
    }


def _delay(error: TouchmarkError, attempt: int) -> float:
    wait = error.retry_after if error.retry_after is not None else attempt + 1
    return min(wait, MAX_RETRY_DELAY_SECONDS)


def _verification_path(verification_id: str) -> str:
    """The API's mailbox-check ids are UUIDs; anything else could reach another path."""
    try:
        canonical = uuid.UUID(str(verification_id))
    except ValueError:
        raise ValueError(
            f"verification_id must be a UUID, not {verification_id!r}"
        ) from None
    return f"/v1/email/verify/{canonical}"


# The calls, shared by both clients.
def _validate_email(email: str) -> _Call[ValidateResponse]:
    return _Call(
        "POST", "/v1/email/validate", ValidateResponse.from_dict, {"email": email}
    )


def _validate_email_batch(emails: list[str]) -> _Call[BatchValidateResponse]:
    return _Call(
        "POST",
        "/v1/email/validate/batch",
        BatchValidateResponse.from_dict,
        {"emails": emails},
    )


def _verify_email(email: str) -> _Call[VerifyResponse]:
    return _Call("POST", "/v1/email/verify", VerifyResponse.from_dict, {"email": email})


def _get_verification(verification_id: str, wait: int | None) -> _Call[VerifyResponse]:
    params = {} if wait is None else {"wait": wait}
    return _Call(
        "GET",
        _verification_path(verification_id),
        VerifyResponse.from_dict,
        params=params,
    )


def _sender_readiness(
    domain: str, dkim_selectors: list[str] | None
) -> _Call[SenderReadinessResponse]:
    body: dict[str, Any] = {"domain": domain}
    if dkim_selectors is not None:
        body["dkim_selectors"] = dkim_selectors
    return _Call(
        "POST", "/v1/domain/sender-readiness", SenderReadinessResponse.from_dict, body
    )


def _lookup_ip(ip: str) -> _Call[LookupResponse]:
    return _Call("POST", "/v1/ip/lookup", LookupResponse.from_dict, {"ip": ip})


def _lookup_ip_batch(ips: list[str]) -> _Call[BatchLookupResponse]:
    return _Call(
        "POST", "/v1/ip/lookup/batch", BatchLookupResponse.from_dict, {"ips": ips}
    )


def _validate_phone(phone: str, country: str | None) -> _Call[PhoneValidateResponse]:
    body: dict[str, Any] = {"phone": phone}
    if country is not None:
        body["country"] = country
    return _Call("POST", "/v1/phone/validate", PhoneValidateResponse.from_dict, body)


def _validate_phone_batch(
    phones: list[str], country: str | None
) -> _Call[PhoneBatchValidateResponse]:
    body: dict[str, Any] = {"phones": phones}
    if country is not None:
        body["country"] = country
    return _Call(
        "POST", "/v1/phone/validate/batch", PhoneBatchValidateResponse.from_dict, body
    )


def _read_account() -> _Call[AccountResponse]:
    return _Call("GET", "/v1/account", AccountResponse.from_dict)


def _next_wait(deadline: float) -> int:
    return max(0, min(MAX_WAIT_SECONDS, int(deadline - time.monotonic() + 0.999)))


class Touchmark:
    """The synchronous client. ``api_key`` defaults to ``TOUCHMARK_API_KEY``."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._headers = _headers(_api_key(api_key))
        # A client you pass in stays yours to close.
        self._owns_http = http_client is None
        self._http = http_client or httpx.Client(timeout=timeout)
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self.email = _Email(self)
        self.domain = _Domain(self)
        self.ip = _Ip(self)
        self.phone = _Phone(self)
        self.account = _Account(self)

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> Touchmark:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _send(self, call: _Call[R], idempotency_key: str | None = None) -> R:
        content, headers = _request(self._headers, call, idempotency_key)
        attempt = 0
        while True:
            try:
                response = self._http.request(
                    call.method,
                    self._base_url + call.path,
                    content=content,
                    params=dict(call.params),
                    headers=headers,
                )
            except httpx.TransportError:
                if attempt >= self._max_retries:
                    raise
                time.sleep(attempt + 1)
                attempt += 1
                continue
            if response.is_success:
                return call.parse(response.json())
            error = _error(response)
            if attempt >= self._max_retries or not _retryable(error):
                raise error
            time.sleep(_delay(error, attempt))
            attempt += 1


class AsyncTouchmark:
    """The asynchronous client (asyncio or trio).

    ``api_key`` defaults to ``TOUCHMARK_API_KEY``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._headers = _headers(_api_key(api_key))
        # A client you pass in stays yours to close.
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=timeout)
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self.email = _AsyncEmail(self)
        self.domain = _AsyncDomain(self)
        self.ip = _AsyncIp(self)
        self.phone = _AsyncPhone(self)
        self.account = _AsyncAccount(self)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> AsyncTouchmark:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def _send(self, call: _Call[R], idempotency_key: str | None = None) -> R:
        content, headers = _request(self._headers, call, idempotency_key)
        attempt = 0
        while True:
            try:
                response = await self._http.request(
                    call.method,
                    self._base_url + call.path,
                    content=content,
                    params=dict(call.params),
                    headers=headers,
                )
            except httpx.TransportError:
                if attempt >= self._max_retries:
                    raise
                await anyio.sleep(attempt + 1)
                attempt += 1
                continue
            if response.is_success:
                return call.parse(response.json())
            error = _error(response)
            if attempt >= self._max_retries or not _retryable(error):
                raise error
            await anyio.sleep(_delay(error, attempt))
            attempt += 1


class _Email:
    def __init__(self, client: Touchmark) -> None:
        self._client = client

    def validate(
        self, email: str, *, idempotency_key: str | None = None
    ) -> ValidateResponse:
        """Syntax, MX, disposable and free-provider domains, role accounts. 1 credit."""
        return self._client._send(_validate_email(email), idempotency_key)

    def validate_batch(
        self, emails: list[str], *, idempotency_key: str | None = None
    ) -> BatchValidateResponse:
        """Up to 100 addresses, answered in order. 1 credit each."""
        return self._client._send(_validate_email_batch(emails), idempotency_key)

    def verify(
        self, email: str, *, idempotency_key: str | None = None
    ) -> VerifyResponse:
        """Starts a mailbox check; a queued answer carries its id. Up to 5 credits."""
        return self._client._send(_verify_email(email), idempotency_key)

    def get_verification(
        self, verification_id: str, *, wait: int | None = None
    ) -> VerifyResponse:
        """A mailbox check, waiting up to ``wait`` seconds (at most 10). Free."""
        return self._client._send(_get_verification(verification_id, wait))

    def wait_for_verification(
        self, verification_id: str, *, timeout: float = 60.0
    ) -> VerifyResponse:
        """Polls a mailbox check until it is done or ``timeout`` seconds pass. Free."""
        deadline = time.monotonic() + timeout
        while True:
            answer = self.get_verification(verification_id, wait=_next_wait(deadline))
            if answer.status == "done" or time.monotonic() >= deadline:
                return answer


class _AsyncEmail:
    def __init__(self, client: AsyncTouchmark) -> None:
        self._client = client

    async def validate(
        self, email: str, *, idempotency_key: str | None = None
    ) -> ValidateResponse:
        """Syntax, MX, disposable and free-provider domains, role accounts. 1 credit."""
        return await self._client._send(_validate_email(email), idempotency_key)

    async def validate_batch(
        self, emails: list[str], *, idempotency_key: str | None = None
    ) -> BatchValidateResponse:
        """Up to 100 addresses, answered in order. 1 credit each."""
        return await self._client._send(_validate_email_batch(emails), idempotency_key)

    async def verify(
        self, email: str, *, idempotency_key: str | None = None
    ) -> VerifyResponse:
        """Starts a mailbox check; a queued answer carries its id. Up to 5 credits."""
        return await self._client._send(_verify_email(email), idempotency_key)

    async def get_verification(
        self, verification_id: str, *, wait: int | None = None
    ) -> VerifyResponse:
        """A mailbox check, waiting up to ``wait`` seconds (at most 10). Free."""
        return await self._client._send(_get_verification(verification_id, wait))

    async def wait_for_verification(
        self, verification_id: str, *, timeout: float = 60.0
    ) -> VerifyResponse:
        """Polls a mailbox check until it is done or ``timeout`` seconds pass. Free."""
        deadline = time.monotonic() + timeout
        while True:
            answer = await self.get_verification(
                verification_id, wait=_next_wait(deadline)
            )
            if answer.status == "done" or time.monotonic() >= deadline:
                return answer


class _Domain:
    def __init__(self, client: Touchmark) -> None:
        self._client = client

    def sender_readiness(
        self,
        domain: str,
        *,
        dkim_selectors: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> SenderReadinessResponse:
        """The domain's DNS against the bulk-sender rules. 2 credits."""
        return self._client._send(
            _sender_readiness(domain, dkim_selectors), idempotency_key
        )


class _AsyncDomain:
    def __init__(self, client: AsyncTouchmark) -> None:
        self._client = client

    async def sender_readiness(
        self,
        domain: str,
        *,
        dkim_selectors: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> SenderReadinessResponse:
        """The domain's DNS against the bulk-sender rules. 2 credits."""
        return await self._client._send(
            _sender_readiness(domain, dkim_selectors), idempotency_key
        )


class _Ip:
    def __init__(self, client: Touchmark) -> None:
        self._client = client

    def lookup(self, ip: str, *, idempotency_key: str | None = None) -> LookupResponse:
        """Country, network owner, hosting company and Tor exit. 1 credit."""
        return self._client._send(_lookup_ip(ip), idempotency_key)

    def lookup_batch(
        self, ips: list[str], *, idempotency_key: str | None = None
    ) -> BatchLookupResponse:
        """Up to 100 addresses, answered in order. 1 credit each."""
        return self._client._send(_lookup_ip_batch(ips), idempotency_key)


class _AsyncIp:
    def __init__(self, client: AsyncTouchmark) -> None:
        self._client = client

    async def lookup(
        self, ip: str, *, idempotency_key: str | None = None
    ) -> LookupResponse:
        """Country, network owner, hosting company and Tor exit. 1 credit."""
        return await self._client._send(_lookup_ip(ip), idempotency_key)

    async def lookup_batch(
        self, ips: list[str], *, idempotency_key: str | None = None
    ) -> BatchLookupResponse:
        """Up to 100 addresses, answered in order. 1 credit each."""
        return await self._client._send(_lookup_ip_batch(ips), idempotency_key)


class _Phone:
    def __init__(self, client: Touchmark) -> None:
        self._client = client

    def validate(
        self,
        phone: str,
        *,
        country: str | None = None,
        idempotency_key: str | None = None,
    ) -> PhoneValidateResponse:
        """Numbering-plan validity, formats, country and line type. 1 credit."""
        return self._client._send(_validate_phone(phone, country), idempotency_key)

    def validate_batch(
        self,
        phones: list[str],
        *,
        country: str | None = None,
        idempotency_key: str | None = None,
    ) -> PhoneBatchValidateResponse:
        """Up to 100 numbers, answered in order. 1 credit each."""
        return self._client._send(
            _validate_phone_batch(phones, country), idempotency_key
        )


class _AsyncPhone:
    def __init__(self, client: AsyncTouchmark) -> None:
        self._client = client

    async def validate(
        self,
        phone: str,
        *,
        country: str | None = None,
        idempotency_key: str | None = None,
    ) -> PhoneValidateResponse:
        """Numbering-plan validity, formats, country and line type. 1 credit."""
        return await self._client._send(
            _validate_phone(phone, country), idempotency_key
        )

    async def validate_batch(
        self,
        phones: list[str],
        *,
        country: str | None = None,
        idempotency_key: str | None = None,
    ) -> PhoneBatchValidateResponse:
        """Up to 100 numbers, answered in order. 1 credit each."""
        return await self._client._send(
            _validate_phone_batch(phones, country), idempotency_key
        )


class _Account:
    def __init__(self, client: Touchmark) -> None:
        self._client = client

    def get(self) -> AccountResponse:
        """The credit balance and tier. Free."""
        return self._client._send(_read_account())


class _AsyncAccount:
    def __init__(self, client: AsyncTouchmark) -> None:
        self._client = client

    async def get(self) -> AccountResponse:
        """The credit balance and tier. Free."""
        return await self._client._send(_read_account())
