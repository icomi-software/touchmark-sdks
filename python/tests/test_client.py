import json
import pickle
import tomllib
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

import touchmark
from touchmark import DEFAULT_BASE_URL, AsyncTouchmark, Touchmark, TouchmarkError
from touchmark.models import (
    AccountResponse,
    LookupResponse,
    PhoneValidateResponse,
    ValidateResponse,
    VerifyResponse,
)

from .conftest import fixture

API = DEFAULT_BASE_URL


def problem(status: int, code: str, **headers: str) -> httpx.Response:
    body = {**fixture("problem_invalid_api_key"), "status": status, "code": code}
    body["detail"] = f"{code} detail"
    return httpx.Response(
        status, json=body, headers={"x-request-id": "req_123", **headers}
    )


def queued(verification_id: str, status: str = "queued") -> dict[str, Any]:
    answer = fixture("verify_email")
    answer.update(id=verification_id, status=status)
    answer["checks"]["mailbox"] = {"status": "pending", "reason": None}
    return answer


# Configuration


def test_the_key_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOUCHMARK_API_KEY", "vld_live_env")
    with respx.mock(base_url=API) as api:
        route = api.get("/v1/account").respond(json=fixture("account"))
        answer = Touchmark().account.get()
    assert isinstance(answer, AccountResponse)
    assert route.calls.last.request.headers["authorization"] == "Bearer vld_live_env"


def test_a_missing_key_is_refused() -> None:
    with pytest.raises(ValueError, match="TOUCHMARK_API_KEY"):
        Touchmark()
    with pytest.raises(ValueError, match="TOUCHMARK_API_KEY"):
        AsyncTouchmark()


def test_another_base_url() -> None:
    with respx.mock(base_url="http://localhost:8000") as api:
        api.get("/v1/account").respond(json=fixture("account"))
        Touchmark("k", base_url="http://localhost:8000/").account.get()


# Methods

SYNC_CASES = [
    (
        "email.validate",
        lambda tm: tm.email.validate("user@example.com"),
        "/v1/email/validate",
        {"email": "user@example.com"},
        "validate_email",
    ),
    (
        "email.validate_batch",
        lambda tm: tm.email.validate_batch(["user@example.com"]),
        "/v1/email/validate/batch",
        {"emails": ["user@example.com"]},
        "validate_email_batch",
    ),
    (
        "email.verify",
        lambda tm: tm.email.verify("user@example.com"),
        "/v1/email/verify",
        {"email": "user@example.com"},
        "verify_email",
    ),
    (
        "domain.sender_readiness",
        lambda tm: tm.domain.sender_readiness("example.com", dkim_selectors=["s1"]),
        "/v1/domain/sender-readiness",
        {"domain": "example.com", "dkim_selectors": ["s1"]},
        "sender_readiness",
    ),
    (
        "ip.lookup",
        lambda tm: tm.ip.lookup("203.0.113.7"),
        "/v1/ip/lookup",
        {"ip": "203.0.113.7"},
        "lookup_ip",
    ),
    (
        "ip.lookup_batch",
        lambda tm: tm.ip.lookup_batch(["203.0.113.7"]),
        "/v1/ip/lookup/batch",
        {"ips": ["203.0.113.7"]},
        "lookup_ip_batch",
    ),
    (
        "phone.validate",
        lambda tm: tm.phone.validate("020 7946 0000", country="GB"),
        "/v1/phone/validate",
        {"phone": "020 7946 0000", "country": "GB"},
        "validate_phone",
    ),
    (
        "phone.validate_batch",
        lambda tm: tm.phone.validate_batch(["+44 20 7946 0000"]),
        "/v1/phone/validate/batch",
        {"phones": ["+44 20 7946 0000"]},
        "validate_phone_batch",
    ),
]


@pytest.mark.parametrize(("name", "call", "path", "body", "answer"), SYNC_CASES)
def test_each_method_sends_its_request(
    name: str, call: Any, path: str, body: dict[str, Any], answer: str
) -> None:
    with respx.mock(base_url=API) as api:
        route = api.post(path).respond(json=fixture(answer))
        result = call(Touchmark("k"))
    request = route.calls.last.request
    assert json.loads(request.content) == body
    assert request.headers["authorization"] == "Bearer k"
    assert result.to_dict() == fixture(answer)


def test_answers_are_typed_models() -> None:
    with respx.mock(base_url=API) as api:
        api.post("/v1/email/validate").respond(json=fixture("validate_email"))
        api.post("/v1/ip/lookup").respond(json=fixture("lookup_ip"))
        api.post("/v1/phone/validate").respond(json=fixture("validate_phone"))
        tm = Touchmark("k")
        email = tm.email.validate("user@example.com")
        ip = tm.ip.lookup("203.0.113.7")
        phone = tm.phone.validate("+44 20 7946 0000")
    assert isinstance(email, ValidateResponse) and email.result == "invalid"
    assert isinstance(ip, LookupResponse) and ip.scope == "private"
    assert isinstance(phone, PhoneValidateResponse) and phone.valid is True


def test_get_verification_passes_the_id_and_wait() -> None:
    verification_id = str(uuid.uuid4())
    with respx.mock(base_url=API) as api:
        route = api.get(f"/v1/email/verify/{verification_id}").respond(
            json=queued(verification_id)
        )
        answer = Touchmark("k").email.get_verification(verification_id, wait=5)
    assert isinstance(answer, VerifyResponse)
    assert route.calls.last.request.url.params["wait"] == "5"


@pytest.mark.parametrize("bad", ["", ".", "..", "../../health", "a/b", "v1"])
def test_a_verification_id_that_is_not_a_uuid_is_refused(bad: str) -> None:
    # respx refuses any request no route matches, so nothing may be sent.
    with respx.mock(base_url=API):
        tm = Touchmark("k")
        with pytest.raises(ValueError, match="UUID"):
            tm.email.get_verification(bad)
        with pytest.raises(ValueError, match="UUID"):
            tm.email.wait_for_verification(bad)


@pytest.mark.anyio
async def test_the_async_client_refuses_an_id_that_is_not_a_uuid() -> None:
    with respx.mock(base_url=API):
        async with AsyncTouchmark("k") as tm:
            with pytest.raises(ValueError, match="UUID"):
                await tm.email.get_verification("..")


# Errors and retries


def test_a_problem_document_becomes_touchmark_error() -> None:
    with respx.mock(base_url=API) as api:
        api.post("/v1/email/validate").mock(
            return_value=problem(402, "insufficient_credits")
        )
        with pytest.raises(TouchmarkError) as raised:
            Touchmark("k").email.validate("user@example.com")
    error = raised.value
    assert (error.status, error.code, error.detail) == (
        402,
        "insufficient_credits",
        "insufficient_credits detail",
    )
    assert (error.request_id, error.retry_after) == ("req_123", None)


def test_an_answer_that_is_not_a_problem_is_named_by_its_status() -> None:
    with respx.mock(base_url=API) as api:
        api.get("/v1/account").respond(502, text="<html>bad gateway</html>")
        with pytest.raises(TouchmarkError) as raised:
            Touchmark("k", max_retries=0).account.get()
    assert (raised.value.code, raised.value.detail) == ("http_502", None)


def test_a_429_is_retried_after_retry_after(sleeps: list[float]) -> None:
    with respx.mock(base_url=API) as api:
        route = api.get("/v1/account").mock(
            side_effect=[
                problem(429, "rate_limited", **{"retry-after": "3"}),
                problem(429, "rate_limited", **{"retry-after": "3"}),
                httpx.Response(200, json=fixture("account")),
            ]
        )
        Touchmark("k").account.get()
    assert route.call_count == 3
    assert sleeps == [3.0, 3.0]


def test_retries_stop_after_two(sleeps: list[float]) -> None:
    with respx.mock(base_url=API) as api:
        route = api.get("/v1/account").mock(
            return_value=problem(429, "rate_limited", **{"retry-after": "1"})
        )
        with pytest.raises(TouchmarkError, match="rate_limited"):
            Touchmark("k").account.get()
    assert route.call_count == 3


def test_a_503_without_retry_after_backs_off(sleeps: list[float]) -> None:
    with respx.mock(base_url=API) as api:
        api.post("/v1/email/validate").mock(
            side_effect=[
                problem(503, "upstream_unavailable"),
                httpx.Response(200, json=fixture("validate_email")),
            ]
        )
        Touchmark("k").email.validate("user@example.com")
    assert sleeps == [1]


def test_a_second_503_waits_two_seconds(sleeps: list[float]) -> None:
    with respx.mock(base_url=API) as api:
        api.post("/v1/email/validate").mock(
            side_effect=[
                problem(503, "upstream_unavailable"),
                problem(503, "upstream_unavailable"),
                httpx.Response(200, json=fixture("validate_email")),
            ]
        )
        Touchmark("k").email.validate("user@example.com")
    assert sleeps == [1, 2]


@pytest.mark.parametrize("value", ["nan", "inf", "-5"])
def test_an_unusable_retry_after_counts_as_none(
    value: str, sleeps: list[float]
) -> None:
    with respx.mock(base_url=API) as api:
        api.get("/v1/account").mock(
            side_effect=[
                problem(429, "rate_limited", **{"retry-after": value}),
                httpx.Response(200, json=fixture("account")),
            ]
        )
        Touchmark("k").account.get()
    assert sleeps == [1]


def test_touchmark_error_survives_pickling() -> None:
    error = TouchmarkError(
        status=429,
        code="rate_limited",
        detail="slow down",
        request_id="req_123",
        retry_after=3.0,
    )
    copy = pickle.loads(pickle.dumps(error))
    fields = (copy.status, copy.code, copy.detail, copy.request_id, copy.retry_after)
    assert fields == (429, "rate_limited", "slow down", "req_123", 3.0)
    assert str(copy) == str(error)


def test_a_long_retry_after_is_capped(sleeps: list[float]) -> None:
    with respx.mock(base_url=API) as api:
        api.get("/v1/account").mock(
            side_effect=[
                problem(429, "rate_limited", **{"retry-after": "3600"}),
                httpx.Response(200, json=fixture("account")),
            ]
        )
        Touchmark("k").account.get()
    assert sleeps == [30.0]


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (402, "insufficient_credits"),
        (400, "invalid_idempotency_key"),
        (422, "idempotency_key_reused"),
        (409, "conflict"),
    ],
)
def test_other_errors_are_not_retried(
    status: int, code: str, sleeps: list[float]
) -> None:
    with respx.mock(base_url=API) as api:
        route = api.post("/v1/email/validate").mock(return_value=problem(status, code))
        with pytest.raises(TouchmarkError):
            Touchmark("k").email.validate("user@example.com")
    assert route.call_count == 1
    assert sleeps == []


@pytest.mark.parametrize(
    "failure",
    [
        problem(500, "internal_error"),
        httpx.Response(502, text="bad gateway"),
        problem(503, "maintenance"),
        httpx.Response(504, text="timeout"),
        problem(409, "idempotency_key_in_use", **{"retry-after": "1"}),
        httpx.ConnectError("down"),
        httpx.ReadTimeout("slow"),
    ],
)
def test_a_failed_call_is_retried_with_the_same_key_and_body(
    failure: httpx.Response | Exception, sleeps: list[float]
) -> None:
    with respx.mock(base_url=API) as api:
        route = api.post("/v1/email/validate").mock(
            side_effect=[failure, httpx.Response(200, json=fixture("validate_email"))]
        )
        Touchmark("k").email.validate("user@example.com")
    first, second = (call.request for call in route.calls)
    assert second.content == first.content
    assert second.headers["idempotency-key"] == first.headers["idempotency-key"]
    assert sleeps == [1.0]


def test_a_network_error_is_raised_after_the_last_retry(sleeps: list[float]) -> None:
    with respx.mock(base_url=API) as api:
        route = api.post("/v1/email/validate").mock(
            side_effect=httpx.ConnectError("down")
        )
        with pytest.raises(httpx.ConnectError):
            Touchmark("k").email.validate("user@example.com")
    assert route.call_count == 3
    assert sleeps == [1.0, 2.0]


def test_each_charged_call_gets_a_new_idempotency_key() -> None:
    with respx.mock(base_url=API) as api:
        route = api.post("/v1/email/validate").respond(json=fixture("validate_email"))
        tm = Touchmark("k")
        tm.email.validate("user@example.com")
        tm.email.validate("user@example.com")
    first, second = (call.request.headers["idempotency-key"] for call in route.calls)
    assert uuid.UUID(first).version == 4
    assert first != second


def test_a_callers_idempotency_key_is_sent() -> None:
    with respx.mock(base_url=API) as api:
        route = api.post("/v1/ip/lookup").respond(json=fixture("lookup_ip"))
        Touchmark("k").ip.lookup("192.0.2.1", idempotency_key="order-42")
    assert route.calls.last.request.headers["idempotency-key"] == "order-42"


def test_a_free_get_sends_no_idempotency_key() -> None:
    with respx.mock(base_url=API) as api:
        route = api.get("/v1/account").respond(json=fixture("account"))
        Touchmark("k").account.get()
    assert "idempotency-key" not in route.calls.last.request.headers


@pytest.mark.anyio
async def test_the_async_client_retries_a_network_error_with_the_same_key(
    sleeps: list[float],
) -> None:
    with respx.mock(base_url=API) as api:
        route = api.post("/v1/phone/validate").mock(
            side_effect=[
                httpx.ConnectError("down"),
                httpx.Response(200, json=fixture("validate_phone")),
            ]
        )
        async with AsyncTouchmark("k") as tm:
            await tm.phone.validate("+44 20 7946 0000", idempotency_key="p-1")
    assert [call.request.headers["idempotency-key"] for call in route.calls] == [
        "p-1",
        "p-1",
    ]
    assert sleeps == [1.0]


def test_max_retries_zero_turns_retries_off(sleeps: list[float]) -> None:
    with respx.mock(base_url=API) as api:
        route = api.get("/v1/account").mock(return_value=problem(429, "rate_limited"))
        with pytest.raises(TouchmarkError):
            Touchmark("k", max_retries=0).account.get()
    assert route.call_count == 1


# Waiting for a mailbox check


def test_wait_for_verification_polls_until_done() -> None:
    verification_id = str(uuid.uuid4())
    done = fixture("verify_email") | {"id": verification_id}
    with respx.mock(base_url=API) as api:
        route = api.get(f"/v1/email/verify/{verification_id}").mock(
            side_effect=[
                httpx.Response(200, json=queued(verification_id)),
                httpx.Response(200, json=queued(verification_id, "running")),
                httpx.Response(200, json=done),
            ]
        )
        answer = Touchmark("k").email.wait_for_verification(verification_id)
    assert answer.status == "done"
    assert route.call_count == 3
    for call in route.calls:
        assert 0 <= int(call.request.url.params["wait"]) <= 10


def test_wait_for_verification_returns_the_last_answer_when_time_is_up() -> None:
    verification_id = str(uuid.uuid4())
    with respx.mock(base_url=API) as api:
        route = api.get(f"/v1/email/verify/{verification_id}").respond(
            json=queued(verification_id)
        )
        answer = Touchmark("k").email.wait_for_verification(verification_id, timeout=0)
    assert answer.status == "queued"
    assert route.call_count == 1


# The asynchronous client


@pytest.mark.anyio
async def test_the_async_client_answers_and_retries(sleeps: list[float]) -> None:
    with respx.mock(base_url=API) as api:
        route = api.post("/v1/phone/validate").mock(
            side_effect=[
                problem(429, "rate_limited", **{"retry-after": "2"}),
                httpx.Response(200, json=fixture("validate_phone")),
            ]
        )
        async with AsyncTouchmark("k") as tm:
            answer = await tm.phone.validate("+44 20 7946 0000")
    assert answer.valid is True
    assert route.call_count == 2
    assert sleeps == [2.0]


@pytest.mark.anyio
async def test_the_async_client_raises_touchmark_error() -> None:
    with respx.mock(base_url=API) as api:
        api.post("/v1/ip/lookup").mock(return_value=problem(422, "validation_error"))
        async with AsyncTouchmark("k") as tm:
            with pytest.raises(TouchmarkError, match="validation_error"):
                await tm.ip.lookup("nope")


@pytest.mark.anyio
async def test_the_async_client_waits_for_a_verification() -> None:
    verification_id = str(uuid.uuid4())
    done = fixture("verify_email") | {"id": verification_id}
    with respx.mock(base_url=API) as api:
        api.get(f"/v1/email/verify/{verification_id}").mock(
            side_effect=[
                httpx.Response(200, json=queued(verification_id)),
                httpx.Response(200, json=done),
            ]
        )
        async with AsyncTouchmark("k") as tm:
            answer = await tm.email.wait_for_verification(verification_id)
    assert answer.status == "done"


@pytest.mark.anyio
@pytest.mark.parametrize(("name", "call", "path", "body", "answer"), SYNC_CASES)
async def test_each_async_method_sends_its_request(
    name: str, call: Any, path: str, body: dict[str, Any], answer: str
) -> None:
    with respx.mock(base_url=API) as api:
        route = api.post(path).respond(json=fixture(answer))
        async with AsyncTouchmark("k") as tm:
            result = await call(tm)
    assert json.loads(route.calls.last.request.content) == body
    assert result.to_dict() == fixture(answer)


# The client's own HTTP connection pool


def test_a_caller_owned_http_client_is_left_open() -> None:
    own = httpx.Client()
    with Touchmark("k", http_client=own):
        pass
    assert not own.is_closed
    own.close()


def test_the_clients_own_http_client_is_closed() -> None:
    tm = Touchmark("k")
    tm.close()
    assert tm._http.is_closed


@pytest.mark.anyio
async def test_a_caller_owned_async_http_client_is_left_open() -> None:
    own = httpx.AsyncClient()
    async with AsyncTouchmark("k", http_client=own):
        pass
    assert not own.is_closed
    await own.aclose()


def test_a_missing_key_builds_no_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[object] = []
    monkeypatch.setattr(
        "touchmark._client.httpx.Client", lambda **kwargs: built.append(kwargs)
    )
    with pytest.raises(ValueError):
        Touchmark()
    assert built == []


@pytest.mark.anyio
async def test_the_async_client_reads_the_account() -> None:
    with respx.mock(base_url=API) as api:
        api.get("/v1/account").respond(json=fixture("account"))
        async with AsyncTouchmark("k") as tm:
            answer = await tm.account.get()
    assert isinstance(answer, AccountResponse)


def test_the_version_is_the_packages() -> None:
    pyproject = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text()
    )
    assert touchmark.__version__ == pyproject["project"]["version"]
