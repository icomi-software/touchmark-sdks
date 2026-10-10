package touchmark

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"testing"
	"time"
)

var uuidV4 = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)

// seen is one request as the fake API received it.
type seen struct {
	method, path, query, body string
	header                    http.Header
}

// fakeAPI answers each request with the next handler; the last one repeats.
type fakeAPI struct {
	mu       sync.Mutex
	handlers []http.HandlerFunc
	requests []seen
}

func (f *fakeAPI) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	f.mu.Lock()
	f.requests = append(f.requests, seen{r.Method, r.URL.Path, r.URL.RawQuery, string(body), r.Header.Clone()})
	handler := f.handlers[0]
	if len(f.handlers) > 1 {
		f.handlers = f.handlers[1:]
	}
	f.mu.Unlock()
	handler(w, r)
}

func reply(status int, body string, headers ...string) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		for i := 0; i+1 < len(headers); i += 2 {
			w.Header().Set(headers[i], headers[i+1])
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = io.WriteString(w, body)
	}
}

func problem(status int, code string, headers ...string) http.HandlerFunc {
	body, _ := json.Marshal(map[string]any{
		"type": "about:blank", "title": code, "status": status,
		"detail": code + " detail", "code": code, "request_id": "req_123",
	})
	return reply(status, string(body), append([]string{"X-Request-Id", "req_123"}, headers...)...)
}

// hangUp closes the connection without an answer: a network error.
func hangUp(w http.ResponseWriter, _ *http.Request) {
	conn, _, _ := w.(http.Hijacker).Hijack()
	_ = conn.Close()
}

func fixture(t *testing.T, name string) string {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("..", "python", "tests", "fixtures", name+".json"))
	if err != nil {
		t.Fatal(err)
	}
	return string(data)
}

// newClient talks to a fake API and records the retry waits instead of sleeping.
func newClient(t *testing.T, api *fakeAPI, options Options) (*Client, *[]time.Duration) {
	t.Helper()
	server := httptest.NewServer(api)
	t.Cleanup(server.Close)
	if options.APIKey == "" {
		options.APIKey = "vld_live_test"
	}
	options.BaseURL = server.URL
	c, err := New(options)
	if err != nil {
		t.Fatal(err)
	}
	waits := &[]time.Duration{}
	c.sleep = func(_ context.Context, d time.Duration) error {
		*waits = append(*waits, d)
		return nil
	}
	return c, waits
}

func TestTheKeyComesFromTheEnvironment(t *testing.T) {
	t.Setenv("TOUCHMARK_API_KEY", "vld_live_env")
	api := &fakeAPI{handlers: []http.HandlerFunc{reply(200, fixture(t, "account"))}}
	server := httptest.NewServer(api)
	defer server.Close()
	c, err := New(Options{BaseURL: server.URL})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := c.Account.Get(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got := api.requests[0].header.Get("Authorization"); got != "Bearer vld_live_env" {
		t.Fatalf("Authorization = %q", got)
	}
}

func TestAMissingKeyIsRefused(t *testing.T) {
	t.Setenv("TOUCHMARK_API_KEY", "")
	if _, err := New(Options{}); err == nil || !strings.Contains(err.Error(), "TOUCHMARK_API_KEY") {
		t.Fatalf("err = %v", err)
	}
}

func TestEachMethodSendsItsRequestAndParsesItsAnswer(t *testing.T) {
	ctx := context.Background()
	cases := []struct {
		name, method, path, body, answer string
		call                             func(*Client) (any, error)
	}{
		{"Email.Validate", "POST", "/v1/email/validate", `{"email":"a@b.co"}`, "validate_email",
			func(c *Client) (any, error) { return c.Email.Validate(ctx, ValidateRequest{Email: "a@b.co"}) }},
		{"Email.ValidateBatch", "POST", "/v1/email/validate/batch", `{"emails":["a@b.co"]}`, "validate_email_batch",
			func(c *Client) (any, error) {
				return c.Email.ValidateBatch(ctx, BatchValidateRequest{Emails: []string{"a@b.co"}})
			}},
		{"Email.Verify", "POST", "/v1/email/verify", `{"email":"a@b.co"}`, "verify_email",
			func(c *Client) (any, error) { return c.Email.Verify(ctx, ValidateRequest{Email: "a@b.co"}) }},
		{"Domain.SenderReadiness", "POST", "/v1/domain/sender-readiness", `{"domain":"acme.com"}`, "sender_readiness",
			func(c *Client) (any, error) {
				return c.Domain.SenderReadiness(ctx, SenderReadinessRequest{Domain: "acme.com"})
			}},
		{"IP.Lookup", "POST", "/v1/ip/lookup", `{"ip":"192.0.2.1"}`, "lookup_ip",
			func(c *Client) (any, error) { return c.IP.Lookup(ctx, LookupRequest{IP: "192.0.2.1"}) }},
		{"IP.LookupBatch", "POST", "/v1/ip/lookup/batch", `{"ips":["192.0.2.1"]}`, "lookup_ip_batch",
			func(c *Client) (any, error) {
				return c.IP.LookupBatch(ctx, BatchLookupRequest{IPs: []string{"192.0.2.1"}})
			}},
		{"Phone.Validate", "POST", "/v1/phone/validate", `{"phone":"020 7946 0000","country":"GB"}`, "validate_phone",
			func(c *Client) (any, error) {
				return c.Phone.Validate(ctx, PhoneValidateRequest{Phone: "020 7946 0000", Country: String("GB")})
			}},
		{"Phone.ValidateBatch", "POST", "/v1/phone/validate/batch", `{"phones":["+442079460000"]}`, "validate_phone_batch",
			func(c *Client) (any, error) {
				return c.Phone.ValidateBatch(ctx, PhoneBatchValidateRequest{Phones: []string{"+442079460000"}})
			}},
		{"Account.Get", "GET", "/v1/account", "", "account",
			func(c *Client) (any, error) { return c.Account.Get(ctx) }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			api := &fakeAPI{handlers: []http.HandlerFunc{reply(200, fixture(t, tc.answer))}}
			c, _ := newClient(t, api, Options{})
			answer, err := tc.call(c)
			if err != nil {
				t.Fatal(err)
			}
			got := api.requests[0]
			if got.method != tc.method || got.path != tc.path || got.body != tc.body {
				t.Fatalf("sent %s %s %s", got.method, got.path, got.body)
			}
			// Every field of the recorded answer is read into the struct.
			want := map[string]any{}
			_ = json.Unmarshal([]byte(fixture(t, tc.answer)), &want)
			back, _ := json.Marshal(answer)
			have := map[string]any{}
			_ = json.Unmarshal(back, &have)
			for key := range want {
				if _, ok := have[key]; !ok {
					t.Errorf("field %q was not parsed", key)
				}
			}
		})
	}
}

func TestGetVerificationPassesTheIDAndWait(t *testing.T) {
	id := "6f1c2c4e-0d2b-4f5e-9a3b-1c2d3e4f5a6b"
	api := &fakeAPI{handlers: []http.HandlerFunc{reply(200, fixture(t, "verify_email"))}}
	c, _ := newClient(t, api, Options{})
	if _, err := c.Email.GetVerification(context.Background(), id, 7); err != nil {
		t.Fatal(err)
	}
	if got := api.requests[0]; got.path != "/v1/email/verify/"+id || got.query != "wait=7" {
		t.Fatalf("sent %s?%s", got.path, got.query)
	}
	for _, bad := range []string{"", "..", "../../health", "a/b"} {
		if _, err := c.Email.GetVerification(context.Background(), bad, 0); err == nil {
			t.Errorf("%q was accepted", bad)
		}
	}
}

func TestWaitForVerificationPollsUntilDone(t *testing.T) {
	queued := strings.Replace(fixture(t, "verify_email"), `"status": "done"`, `"status": "queued"`, 1)
	api := &fakeAPI{handlers: []http.HandlerFunc{reply(202, queued), reply(200, fixture(t, "verify_email"))}}
	c, _ := newClient(t, api, Options{})
	answer, err := c.Email.WaitForVerification(context.Background(), "6f1c2c4e-0d2b-4f5e-9a3b-1c2d3e4f5a6b", time.Minute)
	if err != nil || answer.Status != "done" || len(api.requests) != 2 {
		t.Fatalf("answer %+v, err %v, %d requests", answer, err, len(api.requests))
	}
	if api.requests[0].query != "wait=10" {
		t.Fatalf("first poll %q", api.requests[0].query)
	}
}

func TestWaitForVerificationReturnsTheLastAnswerWhenTimeIsUp(t *testing.T) {
	queued := strings.Replace(fixture(t, "verify_email"), `"status": "done"`, `"status": "queued"`, 1)
	api := &fakeAPI{handlers: []http.HandlerFunc{reply(202, queued)}}
	c, _ := newClient(t, api, Options{})
	answer, err := c.Email.WaitForVerification(context.Background(), "6f1c2c4e-0d2b-4f5e-9a3b-1c2d3e4f5a6b", 0)
	if err != nil || answer.Status != "queued" || api.requests[0].query != "wait=0" {
		t.Fatalf("answer %+v, err %v", answer, err)
	}
}

func TestAProblemDocumentBecomesAnError(t *testing.T) {
	api := &fakeAPI{handlers: []http.HandlerFunc{problem(402, "insufficient_credits")}}
	c, _ := newClient(t, api, Options{})
	answer, err := c.Email.Validate(context.Background(), ValidateRequest{Email: "a@b.co"})
	var apiErr *Error
	if !errors.As(err, &apiErr) {
		t.Fatalf("err = %v", err)
	}
	if answer != nil {
		t.Fatalf("answer = %+v, want nil", answer)
	}
	if apiErr.Status != 402 || apiErr.Code != "insufficient_credits" || apiErr.Detail != "insufficient_credits detail" ||
		apiErr.RequestID != "req_123" || apiErr.RetryAfter != -1 {
		t.Fatalf("%+v", apiErr)
	}
}

func TestAnAnswerThatIsNotAProblemIsNamedByItsStatus(t *testing.T) {
	api := &fakeAPI{handlers: []http.HandlerFunc{reply(502, "<html>bad gateway</html>")}}
	c, _ := newClient(t, api, Options{MaxRetries: -1})
	_, err := c.Account.Get(context.Background())
	var apiErr *Error
	if !errors.As(err, &apiErr) || apiErr.Code != "http_502" || apiErr.Detail != "" {
		t.Fatalf("err = %v", err)
	}
}

func TestChargedCallsSendANewIdempotencyKeyAndGetsSendNone(t *testing.T) {
	api := &fakeAPI{handlers: []http.HandlerFunc{reply(200, fixture(t, "validate_email"))}}
	c, _ := newClient(t, api, Options{})
	ctx := context.Background()
	_, _ = c.Email.Validate(ctx, ValidateRequest{Email: "a@b.co"})
	_, _ = c.Email.Validate(ctx, ValidateRequest{Email: "a@b.co"})
	_, _ = c.IP.Lookup(ctx, LookupRequest{IP: "192.0.2.1"}, WithIdempotencyKey("order-42"))
	first, second := api.requests[0].header.Get("Idempotency-Key"), api.requests[1].header.Get("Idempotency-Key")
	if !uuidV4.MatchString(first) || !uuidV4.MatchString(second) || first == second {
		t.Fatalf("keys %q and %q", first, second)
	}
	if got := api.requests[2].header.Get("Idempotency-Key"); got != "order-42" {
		t.Fatalf("own key sent as %q", got)
	}
	api.handlers = []http.HandlerFunc{reply(200, fixture(t, "account"))}
	_, _ = c.Account.Get(ctx)
	if got := api.requests[3].header.Get("Idempotency-Key"); got != "" {
		t.Fatalf("a GET sent %q", got)
	}
}

func TestAFailedCallIsRetriedWithTheSameKeyAndBody(t *testing.T) {
	failures := map[string]http.HandlerFunc{
		"500":           problem(500, "internal_error"),
		"502":           reply(502, "bad gateway"),
		"503":           problem(503, "maintenance"),
		"504":           reply(504, "timeout"),
		"key in use":    problem(409, "idempotency_key_in_use", "Retry-After", "1"),
		"429":           problem(429, "rate_limited", "Retry-After", "3"),
		"network error": hangUp,
	}
	for name, failure := range failures {
		t.Run(name, func(t *testing.T) {
			api := &fakeAPI{handlers: []http.HandlerFunc{failure, reply(200, fixture(t, "validate_email"))}}
			c, waits := newClient(t, api, Options{})
			if _, err := c.Email.Validate(context.Background(), ValidateRequest{Email: "a@b.co"}); err != nil {
				t.Fatal(err)
			}
			first, second := api.requests[0], api.requests[1]
			if second.body != first.body || second.header.Get("Idempotency-Key") != first.header.Get("Idempotency-Key") {
				t.Fatalf("retry changed: %q %q", first.header.Get("Idempotency-Key"), second.header.Get("Idempotency-Key"))
			}
			want := time.Second
			if name == "429" {
				want = 3 * time.Second
			}
			if len(*waits) != 1 || (*waits)[0] != want {
				t.Fatalf("waits %v", *waits)
			}
		})
	}
}

func TestRetriesWaitOneThenTwoSecondsAndStopAfterTwo(t *testing.T) {
	api := &fakeAPI{handlers: []http.HandlerFunc{problem(503, "upstream_unavailable")}}
	c, waits := newClient(t, api, Options{})
	_, err := c.Account.Get(context.Background())
	var apiErr *Error
	if !errors.As(err, &apiErr) || apiErr.Code != "upstream_unavailable" || len(api.requests) != 3 {
		t.Fatalf("err %v after %d requests", err, len(api.requests))
	}
	if len(*waits) != 2 || (*waits)[0] != time.Second || (*waits)[1] != 2*time.Second {
		t.Fatalf("waits %v", *waits)
	}
}

func TestALongRetryAfterIsCapped(t *testing.T) {
	api := &fakeAPI{handlers: []http.HandlerFunc{problem(429, "rate_limited", "Retry-After", "3600"), reply(200, fixture(t, "account"))}}
	c, waits := newClient(t, api, Options{})
	if _, err := c.Account.Get(context.Background()); err != nil {
		t.Fatal(err)
	}
	if (*waits)[0] != 30*time.Second {
		t.Fatalf("waits %v", *waits)
	}
}

func TestOtherErrorsAreNotRetried(t *testing.T) {
	for _, failure := range []http.HandlerFunc{
		problem(402, "insufficient_credits"),
		problem(400, "invalid_idempotency_key"),
		problem(422, "idempotency_key_reused"),
		problem(409, "conflict"),
	} {
		api := &fakeAPI{handlers: []http.HandlerFunc{failure, reply(200, "{}")}}
		c, _ := newClient(t, api, Options{})
		if _, err := c.Email.Validate(context.Background(), ValidateRequest{Email: "a@b.co"}); err == nil || len(api.requests) != 1 {
			t.Fatalf("err %v after %d requests", err, len(api.requests))
		}
	}
}

func TestANetworkErrorIsReturnedAfterTheLastRetry(t *testing.T) {
	api := &fakeAPI{handlers: []http.HandlerFunc{hangUp}}
	c, _ := newClient(t, api, Options{})
	_, err := c.Email.Validate(context.Background(), ValidateRequest{Email: "a@b.co"})
	var apiErr *Error
	if err == nil || errors.As(err, &apiErr) || len(api.requests) != 3 {
		t.Fatalf("err %v after %d requests", err, len(api.requests))
	}
}

func TestANegativeMaxRetriesTurnsRetriesOff(t *testing.T) {
	api := &fakeAPI{handlers: []http.HandlerFunc{problem(429, "rate_limited", "Retry-After", "0")}}
	c, _ := newClient(t, api, Options{MaxRetries: -1})
	if _, err := c.Account.Get(context.Background()); err == nil || len(api.requests) != 1 {
		t.Fatalf("err %v after %d requests", err, len(api.requests))
	}
}

func TestARedirectIsNotFollowed(t *testing.T) {
	api := &fakeAPI{handlers: []http.HandlerFunc{reply(307, "", "Location", "https://elsewhere.example/")}}
	c, _ := newClient(t, api, Options{})
	_, err := c.Account.Get(context.Background())
	var apiErr *Error
	if !errors.As(err, &apiErr) || apiErr.Status != 307 || len(api.requests) != 1 {
		t.Fatalf("err %v after %d requests", err, len(api.requests))
	}
}

func TestAnUnreadableAnswerIsNotRetried(t *testing.T) {
	api := &fakeAPI{handlers: []http.HandlerFunc{reply(200, "not json")}}
	c, _ := newClient(t, api, Options{})
	if _, err := c.Account.Get(context.Background()); err == nil || len(api.requests) != 1 {
		t.Fatalf("err %v after %d requests", err, len(api.requests))
	}
}
