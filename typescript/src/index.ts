/**
 * The Touchmark API client. Types come from the API's OpenAPI document
 * (src/gen, generated); the requests, errors and retries are written here.
 */
import type * as T from "./gen/types.gen.js"

export type * from "./gen/types.gen.js"

export const DEFAULT_BASE_URL = "https://api.touchmark.dev"
/**
 * Retries of a call that failed on the way or got a 429, 409
 * idempotency_key_in_use or 5xx answer. Charged calls carry an
 * Idempotency-Key, so a retry is charged at most once.
 */
export const DEFAULT_MAX_RETRIES = 2
/** The API's longest long poll for a mailbox check. */
export const MAX_WAIT_SECONDS = 10
const MAX_RETRY_DELAY_SECONDS = 30

export interface TouchmarkOptions {
  /** API key (vld_live_…). Defaults to the TOUCHMARK_API_KEY environment variable. */
  apiKey?: string
  /** Defaults to https://api.touchmark.dev. */
  baseUrl?: string
  /** Retries of network errors and of 429, 409 in-use and 5xx answers; 0 turns them off. */
  maxRetries?: number
  /** A fetch implementation; defaults to the global fetch. */
  fetch?: typeof fetch
}

/** Options of a charged call. */
export interface CallOptions {
  /**
   * Sent as the Idempotency-Key header: the API charges the call at most once
   * per key and body for 24 hours. Defaults to a new random key per call, the
   * same on each retry; pass your own to retry safely across processes.
   */
  idempotencyKey?: string
}

/** Any answer that is not 2xx, read from the API's problem document. */
export class TouchmarkError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: string | null
  readonly requestId: string | null
  readonly retryAfter: number | null

  constructor(init: {
    status: number
    code: string
    detail: string | null
    requestId: string | null
    retryAfter: number | null
  }) {
    super(`${init.code}: ${init.detail ?? `HTTP ${init.status}`}`)
    this.name = "TouchmarkError"
    this.status = init.status
    this.code = init.code
    this.detail = init.detail
    this.requestId = init.requestId
    this.retryAfter = init.retryAfter
  }
}

type Query = Record<string, string | number>

function environmentKey(): string | undefined {
  const process = (
    globalThis as { process?: { env?: Record<string, string | undefined> } }
  ).process
  return process?.env?.TOUCHMARK_API_KEY
}

function retryAfterSeconds(response: Response): number | null {
  const value = response.headers.get("retry-after")
  if (value === null) return null
  const seconds = Number(value)
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null
}

// The API's mailbox-check ids are UUIDs; anything else could reach another path.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function verificationPath(verificationId: string): string {
  if (!UUID.test(verificationId)) {
    throw new TypeError(
      `verificationId must be a UUID, not ${JSON.stringify(verificationId)}`,
    )
  }
  return `/v1/email/verify/${verificationId}`
}

function retryable(error: TouchmarkError): boolean {
  return (
    error.status === 429 ||
    (error.status === 409 && error.code === "idempotency_key_in_use") ||
    [500, 502, 503, 504].includes(error.status)
  )
}

const sleep = (seconds: number) =>
  new Promise((resolve) => setTimeout(resolve, seconds * 1000))

export class Touchmark {
  readonly #apiKey: string
  readonly #baseUrl: string
  readonly #maxRetries: number
  readonly #fetch: typeof fetch

  constructor(options: TouchmarkOptions = {}) {
    const apiKey = options.apiKey ?? environmentKey()
    if (!apiKey) {
      throw new Error(
        "Touchmark: pass apiKey or set the TOUCHMARK_API_KEY environment variable.",
      )
    }
    this.#apiKey = apiKey
    this.#baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "")
    this.#maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES
    this.#fetch = options.fetch ?? globalThis.fetch.bind(globalThis)
  }

  readonly email = {
    /** Syntax, MX, disposable and free-provider domains, role accounts. 1 credit. */
    validate: (body: T.ValidateEmailData["body"], options: CallOptions = {}) =>
      this.#request<T.ValidateEmailResponses[200]>(
        "POST",
        "/v1/email/validate",
        body,
        undefined,
        options.idempotencyKey,
      ),
    /** Up to 100 addresses, answered in order. 1 credit each. */
    validateBatch: (
      body: T.ValidateEmailBatchData["body"],
      options: CallOptions = {},
    ) =>
      this.#request<T.ValidateEmailBatchResponses[200]>(
        "POST",
        "/v1/email/validate/batch",
        body,
        undefined,
        options.idempotencyKey,
      ),
    /** Starts a mailbox check; a queued answer carries its id. Up to 5 credits. */
    verify: (body: T.VerifyEmailData["body"], options: CallOptions = {}) =>
      this.#request<T.VerifyEmailResponse>(
        "POST",
        "/v1/email/verify",
        body,
        undefined,
        options.idempotencyKey,
      ),
    /** A mailbox check, waiting up to `wait` seconds (at most 10) for it to finish. Free. */
    getVerification: async (
      verificationId: string,
      options: { wait?: number } = {},
    ) =>
      this.#request<T.GetVerificationResponses[200]>(
        "GET",
        verificationPath(verificationId),
        undefined,
        options.wait === undefined ? undefined : { wait: options.wait },
      ),
    /** Polls a mailbox check until it is done or `timeoutSeconds` pass; the last answer. Free. */
    waitForVerification: async (
      verificationId: string,
      options: { timeoutSeconds?: number } = {},
    ) => {
      const deadline = Date.now() + (options.timeoutSeconds ?? 60) * 1000
      for (;;) {
        const left = Math.ceil((deadline - Date.now()) / 1000)
        const wait = Math.min(MAX_WAIT_SECONDS, Math.max(left, 0))
        const answer = await this.email.getVerification(verificationId, {
          wait,
        })
        if (answer.status === "done" || Date.now() >= deadline) return answer
      }
    },
  }

  readonly domain = {
    /** The domain's DNS against the Gmail, Yahoo and Microsoft sender rules. 2 credits. */
    senderReadiness: (
      body: T.SenderReadinessData["body"],
      options: CallOptions = {},
    ) =>
      this.#request<T.SenderReadinessResponses[200]>(
        "POST",
        "/v1/domain/sender-readiness",
        body,
        undefined,
        options.idempotencyKey,
      ),
  }

  readonly ip = {
    /** Country, network owner, hosting company and Tor exit. 1 credit. */
    lookup: (body: T.LookupIpData["body"], options: CallOptions = {}) =>
      this.#request<T.LookupIpResponses[200]>(
        "POST",
        "/v1/ip/lookup",
        body,
        undefined,
        options.idempotencyKey,
      ),
    /** Up to 100 addresses, answered in order. 1 credit each. */
    lookupBatch: (
      body: T.LookupIpBatchData["body"],
      options: CallOptions = {},
    ) =>
      this.#request<T.LookupIpBatchResponses[200]>(
        "POST",
        "/v1/ip/lookup/batch",
        body,
        undefined,
        options.idempotencyKey,
      ),
  }

  readonly phone = {
    /** Numbering-plan validity, formats, country and line type. 1 credit. */
    validate: (body: T.ValidatePhoneData["body"], options: CallOptions = {}) =>
      this.#request<T.ValidatePhoneResponses[200]>(
        "POST",
        "/v1/phone/validate",
        body,
        undefined,
        options.idempotencyKey,
      ),
    /** Up to 100 numbers, answered in order. 1 credit each. */
    validateBatch: (
      body: T.ValidatePhoneBatchData["body"],
      options: CallOptions = {},
    ) =>
      this.#request<T.ValidatePhoneBatchResponses[200]>(
        "POST",
        "/v1/phone/validate/batch",
        body,
        undefined,
        options.idempotencyKey,
      ),
  }

  readonly account = {
    /** The credit balance and tier. Free. */
    get: () => this.#request<T.ReadAccountResponses[200]>("GET", "/v1/account"),
  }

  async #request<R>(
    method: "GET" | "POST",
    path: string,
    body?: unknown,
    query?: Query,
    idempotencyKey?: string,
  ): Promise<R> {
    const url = new URL(this.#baseUrl + path)
    for (const [name, value] of Object.entries(query ?? {})) {
      url.searchParams.set(name, String(value))
    }
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.#apiKey}`,
      Accept: "application/json",
    }
    // Every POST is charged: its key and bytes stay the same on each retry, so
    // the API charges it at most once.
    const payload = body === undefined ? undefined : JSON.stringify(body)
    if (payload !== undefined) {
      headers["Content-Type"] = "application/json"
      headers["Idempotency-Key"] =
        idempotencyKey || globalThis.crypto.randomUUID()
    }
    for (let attempt = 0; ; attempt++) {
      let response: Response
      let text = ""
      try {
        response = await this.#fetch(url, {
          method,
          headers,
          redirect: "manual", // never send the key or body to another origin
          body: payload,
        })
        // A body lost on the wire is a network error: retry with the same key.
        if (response.ok) text = await response.text()
      } catch (error) {
        if (attempt >= this.#maxRetries) throw error
        await sleep(attempt + 1)
        continue
      }
      if (response.ok) return JSON.parse(text) as R
      const error = await toError(response)
      if (attempt >= this.#maxRetries || !retryable(error)) throw error
      await sleep(
        Math.min(error.retryAfter ?? attempt + 1, MAX_RETRY_DELAY_SECONDS),
      )
    }
  }
}

async function toError(response: Response): Promise<TouchmarkError> {
  let problem: { code?: unknown; detail?: unknown } = {}
  try {
    const body: unknown = await response.json()
    // JSON null or an array is not a problem document either.
    if (body !== null && typeof body === "object") problem = body
  } catch {
    // Not a problem document (a proxy's error page, for example).
  }
  return new TouchmarkError({
    status: response.status,
    code:
      typeof problem.code === "string"
        ? problem.code
        : `http_${response.status}`,
    detail: typeof problem.detail === "string" ? problem.detail : null,
    requestId: response.headers.get("x-request-id"),
    retryAfter: retryAfterSeconds(response),
  })
}
