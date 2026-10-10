import { afterEach, describe, expect, it, vi } from "vitest"

import { DEFAULT_BASE_URL, Touchmark, TouchmarkError } from "../src/index.js"

type Call = { url: URL; init: RequestInit }

const ID = "6f1c2c4e-0d2b-4f5e-9a3b-1c2d3e4f5a6b"
const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

function header(init: RequestInit | undefined, name: string) {
  return (init?.headers as Record<string, string> | undefined)?.[
    Object.keys(init?.headers ?? {}).find(
      (key) => key.toLowerCase() === name,
    ) ?? ""
  ]
}

function json(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  })
}

function fakeFetch(...answers: (Response | Error)[]) {
  const calls: Call[] = []
  const fetch = async (url: URL | RequestInfo, init?: RequestInit) => {
    calls.push({ url: new URL(String(url)), init: init ?? {} })
    const answer = answers.shift()
    if (answer === undefined) throw new Error("no answer left")
    if (answer instanceof Error) throw answer
    return answer
  }
  return { calls, fetch: fetch as typeof globalThis.fetch }
}

function problem(
  status: number,
  code: string,
  headers: Record<string, string> = {},
) {
  return json(
    status,
    {
      type: "about:blank",
      title: code,
      status,
      detail: `${code} detail`,
      code,
    },
    { "x-request-id": "req_123", ...headers },
  )
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.useRealTimers()
})

describe("configuration", () => {
  it("reads the key from TOUCHMARK_API_KEY", async () => {
    vi.stubEnv("TOUCHMARK_API_KEY", "vld_live_env")
    const { calls, fetch } = fakeFetch(
      json(200, { credit_balance: 5, tier: 0 }),
    )
    await new Touchmark({ fetch }).account.get()
    expect(calls[0]?.init.headers).toMatchObject({
      Authorization: "Bearer vld_live_env",
    })
    expect(calls[0]?.url.toString()).toBe(`${DEFAULT_BASE_URL}/v1/account`)
  })

  it("refuses to start without a key", () => {
    vi.stubEnv("TOUCHMARK_API_KEY", "")
    expect(() => new Touchmark()).toThrow(/TOUCHMARK_API_KEY/)
  })

  it("takes another base URL", async () => {
    const { calls, fetch } = fakeFetch(json(200, {}))
    await new Touchmark({
      apiKey: "k",
      baseUrl: "http://localhost:8000/",
      fetch,
    }).account.get()
    expect(calls[0]?.url.toString()).toBe("http://localhost:8000/v1/account")
  })
})

describe("methods", () => {
  const cases: [
    string,
    (tm: Touchmark) => Promise<unknown>,
    string,
    string,
    unknown,
  ][] = [
    [
      "email.validate",
      (tm) => tm.email.validate({ email: "a@b.co" }),
      "POST",
      "/v1/email/validate",
      { email: "a@b.co" },
    ],
    [
      "email.validateBatch",
      (tm) => tm.email.validateBatch({ emails: ["a@b.co"] }),
      "POST",
      "/v1/email/validate/batch",
      { emails: ["a@b.co"] },
    ],
    [
      "email.verify",
      (tm) => tm.email.verify({ email: "a@b.co" }),
      "POST",
      "/v1/email/verify",
      { email: "a@b.co" },
    ],
    [
      "domain.senderReadiness",
      (tm) => tm.domain.senderReadiness({ domain: "b.co" }),
      "POST",
      "/v1/domain/sender-readiness",
      { domain: "b.co" },
    ],
    [
      "ip.lookup",
      (tm) => tm.ip.lookup({ ip: "203.0.113.7" }),
      "POST",
      "/v1/ip/lookup",
      { ip: "203.0.113.7" },
    ],
    [
      "ip.lookupBatch",
      (tm) => tm.ip.lookupBatch({ ips: ["203.0.113.7"] }),
      "POST",
      "/v1/ip/lookup/batch",
      { ips: ["203.0.113.7"] },
    ],
    [
      "phone.validate",
      (tm) => tm.phone.validate({ phone: "+44 20 7946 0000" }),
      "POST",
      "/v1/phone/validate",
      { phone: "+44 20 7946 0000" },
    ],
    [
      "phone.validateBatch",
      (tm) =>
        tm.phone.validateBatch({ phones: ["+44 20 7946 0000"], country: "GB" }),
      "POST",
      "/v1/phone/validate/batch",
      { phones: ["+44 20 7946 0000"], country: "GB" },
    ],
  ]

  it.each(cases)(
    "%s sends its request",
    async (_, call, method, path, body) => {
      const { calls, fetch } = fakeFetch(json(200, { ok: true }))
      const answer = await call(new Touchmark({ apiKey: "k", fetch }))
      expect(answer).toEqual({ ok: true })
      expect(calls[0]?.init.method).toBe(method)
      expect(calls[0]?.url.pathname).toBe(path)
      expect(JSON.parse(String(calls[0]?.init.body))).toEqual(body)
      expect(calls[0]?.init.headers).toMatchObject({
        "Content-Type": "application/json",
      })
    },
  )

  it("email.getVerification passes the id and wait", async () => {
    const { calls, fetch } = fakeFetch(json(200, { status: "done" }))
    await new Touchmark({ apiKey: "k", fetch }).email.getVerification(ID, {
      wait: 5,
    })
    expect(calls[0]?.url.pathname).toBe(`/v1/email/verify/${ID}`)
    expect(calls[0]?.url.searchParams.get("wait")).toBe("5")
    expect(calls[0]?.init.body).toBeUndefined()
  })

  it.each(["", ".", "..", "../../health", "a/b", "v1"])(
    "refuses the verification id %j before sending",
    async (id) => {
      const { calls, fetch } = fakeFetch(json(200, { status: "done" }))
      const tm = new Touchmark({ apiKey: "k", fetch })
      await expect(tm.email.getVerification(id)).rejects.toThrow(TypeError)
      await expect(tm.email.waitForVerification(id)).rejects.toThrow(TypeError)
      expect(calls).toHaveLength(0)
    },
  )
})

describe("errors and retries", () => {
  it("turns a problem document into TouchmarkError", async () => {
    const { fetch } = fakeFetch(problem(402, "insufficient_credits"))
    const error = await new Touchmark({ apiKey: "k", fetch }).email
      .validate({ email: "a@b.co" })
      .catch((e: unknown) => e)
    expect(error).toBeInstanceOf(TouchmarkError)
    expect(error).toMatchObject({
      status: 402,
      code: "insufficient_credits",
      detail: "insufficient_credits detail",
      requestId: "req_123",
      retryAfter: null,
    })
  })

  it("names an answer that is not a problem document by its status", async () => {
    const { fetch } = fakeFetch(
      new Response("<html>bad gateway</html>", { status: 502 }),
    )
    await expect(
      new Touchmark({ apiKey: "k", fetch, maxRetries: 0 }).account.get(),
    ).rejects.toMatchObject({ status: 502, code: "http_502", detail: null })
  })

  it("retries a 429 after Retry-After, at most twice", async () => {
    const { calls, fetch } = fakeFetch(
      problem(429, "rate_limited", { "retry-after": "0" }),
      problem(429, "rate_limited", { "retry-after": "0" }),
      json(200, { ok: true }),
    )
    await expect(
      new Touchmark({ apiKey: "k", fetch }).account.get(),
    ).resolves.toEqual({ ok: true })
    expect(calls).toHaveLength(3)
  })

  it("gives up after two retries", async () => {
    const { calls, fetch } = fakeFetch(
      problem(429, "rate_limited", { "retry-after": "0" }),
      problem(429, "rate_limited", { "retry-after": "0" }),
      problem(429, "rate_limited", { "retry-after": "0" }),
    )
    await expect(
      new Touchmark({ apiKey: "k", fetch }).account.get(),
    ).rejects.toMatchObject({
      code: "rate_limited",
      retryAfter: 0,
    })
    expect(calls).toHaveLength(3)
  })

  it("names an error body that is not an object by its status", async () => {
    const { fetch } = fakeFetch(json(500, null))
    await expect(
      new Touchmark({ apiKey: "k", fetch, maxRetries: 0 }).account.get(),
    ).rejects.toMatchObject({ status: 500, code: "http_500", detail: null })
  })

  it("waits 1 s, then 2 s, before retrying a 503 without Retry-After", async () => {
    vi.useFakeTimers()
    const { calls, fetch } = fakeFetch(
      problem(503, "upstream_unavailable"),
      problem(503, "upstream_unavailable"),
      json(200, { ok: true }),
    )
    const pending = new Touchmark({ apiKey: "k", fetch }).email.validate({
      email: "a@b.co",
    })
    await vi.advanceTimersByTimeAsync(999)
    expect(calls).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(calls).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(1999)
    expect(calls).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(1)
    await expect(pending).resolves.toEqual({ ok: true })
    expect(calls).toHaveLength(3)
  })

  it("caps a long Retry-After at 30 s", async () => {
    vi.useFakeTimers()
    const { calls, fetch } = fakeFetch(
      problem(429, "rate_limited", { "retry-after": "3600" }),
      json(200, { ok: true }),
    )
    const pending = new Touchmark({ apiKey: "k", fetch }).account.get()
    await vi.advanceTimersByTimeAsync(29_999)
    expect(calls).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    await expect(pending).resolves.toEqual({ ok: true })
    expect(calls).toHaveLength(2)
  })

  it.each([
    ["a 402", problem(402, "insufficient_credits")],
    ["a 400", problem(400, "invalid_idempotency_key")],
    ["a reused key", problem(422, "idempotency_key_reused")],
    ["another 409", problem(409, "conflict")],
  ])("does not retry %s", async (_, answer) => {
    const { calls, fetch } = fakeFetch(answer, json(200, {}))
    await expect(
      new Touchmark({ apiKey: "k", fetch }).email.validate({ email: "a@b.co" }),
    ).rejects.toBeInstanceOf(TouchmarkError)
    expect(calls).toHaveLength(1)
  })

  it.each([
    ["a 500", problem(500, "internal_error")],
    ["a 502", new Response("bad gateway", { status: 502 })],
    ["any 503", problem(503, "maintenance")],
    ["a 504", new Response("timeout", { status: 504 })],
    [
      "a key in use",
      problem(409, "idempotency_key_in_use", { "retry-after": "0" }),
    ],
    ["a network error", new TypeError("network down")],
  ])("retries %s with the same key and body", async (_, answer) => {
    vi.useFakeTimers()
    const { calls, fetch } = fakeFetch(answer, json(200, { ok: true }))
    const pending = new Touchmark({ apiKey: "k", fetch }).email.validate({
      email: "a@b.co",
    })
    await vi.advanceTimersByTimeAsync(1000)
    await expect(pending).resolves.toEqual({ ok: true })
    expect(calls).toHaveLength(2)
    const [first, second] = calls.map((call) => call.init)
    expect(second?.body).toBe(first?.body)
    expect(header(second, "idempotency-key")).toBe(
      header(first, "idempotency-key"),
    )
  })

  it("throws the network error after the last retry", async () => {
    vi.useFakeTimers()
    const { calls, fetch } = fakeFetch(
      new TypeError("network down"),
      new TypeError("network down"),
      new TypeError("network down"),
    )
    const pending = new Touchmark({ apiKey: "k", fetch }).email
      .validate({ email: "a@b.co" })
      .catch((e: unknown) => e)
    await vi.advanceTimersByTimeAsync(3000)
    expect(await pending).toBeInstanceOf(TypeError)
    expect(calls).toHaveLength(3)
  })

  it("sends a new random Idempotency-Key with each charged call", async () => {
    const { calls, fetch } = fakeFetch(json(200, {}), json(200, {}))
    const tm = new Touchmark({ apiKey: "k", fetch })
    await tm.email.validate({ email: "a@b.co" })
    await tm.email.validate({ email: "a@b.co" })
    const [first, second] = calls.map((call) =>
      header(call.init, "idempotency-key"),
    )
    expect(first).toMatch(UUID_V4)
    expect(second).toMatch(UUID_V4)
    expect(second).not.toBe(first)
  })

  it("sends a random Idempotency-Key when the caller's is empty", async () => {
    const { calls, fetch } = fakeFetch(json(200, {}))
    await new Touchmark({ apiKey: "k", fetch }).ip.lookup(
      { ip: "192.0.2.1" },
      { idempotencyKey: "" },
    )
    expect(header(calls[0]?.init, "idempotency-key")).toMatch(UUID_V4)
  })

  it("retries a 2xx whose body is lost, with the same key and bytes", async () => {
    vi.useFakeTimers()
    const lost = json(200, {})
    lost.text = () => Promise.reject(new TypeError("terminated"))
    const { calls, fetch } = fakeFetch(lost, json(200, { ok: true }))
    const pending = new Touchmark({ apiKey: "k", fetch }).email.validate({
      email: "a@b.co",
    })
    await vi.advanceTimersByTimeAsync(1000)
    expect(await pending).toEqual({ ok: true })
    expect(calls).toHaveLength(2)
    expect(header(calls[1]?.init, "idempotency-key")).toBe(
      header(calls[0]?.init, "idempotency-key"),
    )
    expect(calls[1]?.init.body).toBe(calls[0]?.init.body)
  })

  it("does not retry a 2xx whose body is not JSON", async () => {
    const { calls, fetch } = fakeFetch(
      new Response("<html>", { status: 200 }),
      json(200, {}),
    )
    await expect(
      new Touchmark({ apiKey: "k", fetch }).email.validate({ email: "a@b.co" }),
    ).rejects.toBeInstanceOf(SyntaxError)
    expect(calls).toHaveLength(1)
  })

  it("sends the caller's own Idempotency-Key", async () => {
    const { calls, fetch } = fakeFetch(json(200, {}))
    await new Touchmark({ apiKey: "k", fetch }).ip.lookup(
      { ip: "192.0.2.1" },
      { idempotencyKey: "order-42" },
    )
    expect(header(calls[0]?.init, "idempotency-key")).toBe("order-42")
  })

  it("sends no Idempotency-Key with a free GET", async () => {
    const { calls, fetch } = fakeFetch(json(200, {}))
    await new Touchmark({ apiKey: "k", fetch }).account.get()
    expect(header(calls[0]?.init, "idempotency-key")).toBeUndefined()
  })

  it("does not follow a redirect", async () => {
    const { calls, fetch } = fakeFetch(
      new Response(null, {
        status: 307,
        headers: { location: "https://elsewhere.example" },
      }),
    )
    const error = await new Touchmark({ apiKey: "k", fetch }).account
      .get()
      .catch((e) => e)
    expect(error).toBeInstanceOf(TouchmarkError)
    expect(error.status).toBe(307)
    expect(error.code).toBe("http_307")
    expect(calls).toHaveLength(1)
    expect(calls[0]?.init.redirect).toBe("manual")
  })

  it("maxRetries: 0 turns retries off", async () => {
    const { calls, fetch } = fakeFetch(
      problem(429, "rate_limited", { "retry-after": "0" }),
    )
    await expect(
      new Touchmark({ apiKey: "k", fetch, maxRetries: 0 }).account.get(),
    ).rejects.toBeInstanceOf(TouchmarkError)
    expect(calls).toHaveLength(1)
  })
})

describe("waitForVerification", () => {
  it("polls until the check is done", async () => {
    const { calls, fetch } = fakeFetch(
      json(200, { id: ID, status: "queued" }),
      json(200, { id: ID, status: "running" }),
      json(200, { id: ID, status: "done", result: "valid" }),
    )
    const answer = await new Touchmark({
      apiKey: "k",
      fetch,
    }).email.waitForVerification(ID)
    expect(answer).toMatchObject({ status: "done", result: "valid" })
    expect(calls).toHaveLength(3)
    for (const call of calls) {
      const wait = Number(call.url.searchParams.get("wait"))
      expect(wait).toBeGreaterThanOrEqual(0)
      expect(wait).toBeLessThanOrEqual(10)
    }
  })

  it("returns the last answer when the time is up", async () => {
    const { calls, fetch } = fakeFetch(json(200, { id: ID, status: "queued" }))
    const answer = await new Touchmark({
      apiKey: "k",
      fetch,
    }).email.waitForVerification(ID, {
      timeoutSeconds: 0,
    })
    expect(answer).toMatchObject({ status: "queued" })
    expect(calls).toHaveLength(1)
  })
})
