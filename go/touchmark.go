// Package touchmark is the Touchmark API client: email validation and mailbox
// checks, sender readiness, IP lookup and phone number validation.
//
// Types come from the API's OpenAPI document (types.gen.go, generated); the
// requests, errors and retries are written here.
package touchmark

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	// DefaultBaseURL is the Touchmark API.
	DefaultBaseURL = "https://api.touchmark.dev"
	// DefaultMaxRetries is how often a call that failed on the way, or got a
	// 429, 409 idempotency_key_in_use or 5xx answer, is retried. Charged calls
	// carry an Idempotency-Key, so a retry is charged at most once.
	DefaultMaxRetries = 2
	// MaxWaitSeconds is the API's longest long poll for a mailbox check.
	MaxWaitSeconds = 10

	maxRetryDelay = 30 * time.Second
	userAgent     = "touchmark-go/0.1.0"
)

// Options configure a Client. Every field is optional.
type Options struct {
	// APIKey (vld_live_…) defaults to the TOUCHMARK_API_KEY environment variable.
	APIKey string
	// BaseURL defaults to DefaultBaseURL.
	BaseURL string
	// MaxRetries defaults to DefaultMaxRetries; a negative value turns retries off.
	MaxRetries int
	// HTTPClient defaults to a client with a 30-second timeout. The Client
	// never follows redirects, so the key is never sent to another origin.
	HTTPClient *http.Client
}

// Error is any answer that is not 2xx, read from the API's problem document.
type Error struct {
	Status int
	// Code is stable: match on it. An answer that is not a problem document
	// gets http_<status>.
	Code      string
	Detail    string
	RequestID string
	// RetryAfter is the Retry-After header, or -1 without one.
	RetryAfter time.Duration
}

func (e *Error) Error() string {
	if e.Detail == "" {
		return fmt.Sprintf("touchmark: %s: HTTP %d", e.Code, e.Status)
	}
	return fmt.Sprintf("touchmark: %s: %s", e.Code, e.Detail)
}

// Client calls the Touchmark API. It is safe for concurrent use.
type Client struct {
	apiKey     string
	baseURL    string
	maxRetries int
	http       *http.Client
	sleep      func(context.Context, time.Duration) error

	Email   *EmailService
	Domain  *DomainService
	IP      *IPService
	Phone   *PhoneService
	Account *AccountService
}

// New makes a Client; it fails without an API key.
func New(options Options) (*Client, error) {
	key := options.APIKey
	if key == "" {
		key = os.Getenv("TOUCHMARK_API_KEY")
	}
	if key == "" {
		return nil, errors.New("touchmark: set Options.APIKey or the TOUCHMARK_API_KEY environment variable")
	}
	base := options.BaseURL
	if base == "" {
		base = DefaultBaseURL
	}
	retries := options.MaxRetries
	if retries == 0 {
		retries = DefaultMaxRetries
	} else if retries < 0 {
		retries = 0
	}
	httpClient := &http.Client{Timeout: 30 * time.Second}
	if options.HTTPClient != nil {
		copied := *options.HTTPClient
		httpClient = &copied
	}
	httpClient.CheckRedirect = func(*http.Request, []*http.Request) error {
		return http.ErrUseLastResponse
	}
	c := &Client{
		apiKey:     key,
		baseURL:    strings.TrimRight(base, "/"),
		maxRetries: retries,
		http:       httpClient,
		sleep:      sleep,
	}
	c.Email = &EmailService{c}
	c.Domain = &DomainService{c}
	c.IP = &IPService{c}
	c.Phone = &PhoneService{c}
	c.Account = &AccountService{c}
	return c, nil
}

// A CallOption changes one charged call.
type CallOption func(*callOptions)

type callOptions struct{ idempotencyKey string }

// WithIdempotencyKey sends key as the call's Idempotency-Key: the API charges
// the call at most once per key and body for 24 hours. Without it, each call
// gets a new random key, the same on each of its retries.
func WithIdempotencyKey(key string) CallOption {
	return func(o *callOptions) { o.idempotencyKey = key }
}

// String returns a pointer to s, for optional fields such as Country.
func String(s string) *string { return &s }

// EmailService holds the email calls.
type EmailService struct{ c *Client }

// Validate checks syntax, MX, disposable and free-provider domains and role accounts. 1 credit.
func (s *EmailService) Validate(ctx context.Context, body ValidateRequest, options ...CallOption) (*ValidateResponse, error) {
	var answer ValidateResponse
	return &answer, s.c.post(ctx, "/v1/email/validate", body, &answer, options)
}

// ValidateBatch validates up to 100 addresses, answered in order. 1 credit each.
func (s *EmailService) ValidateBatch(ctx context.Context, body BatchValidateRequest, options ...CallOption) (*BatchValidateResponse, error) {
	var answer BatchValidateResponse
	return &answer, s.c.post(ctx, "/v1/email/validate/batch", body, &answer, options)
}

// Verify starts a mailbox check; a queued answer carries its ID. Up to 5 credits.
func (s *EmailService) Verify(ctx context.Context, body ValidateRequest, options ...CallOption) (*VerifyResponse, error) {
	var answer VerifyResponse
	return &answer, s.c.post(ctx, "/v1/email/verify", body, &answer, options)
}

var uuidPattern = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

// GetVerification reads a mailbox check, waiting up to wait seconds (at most
// 10; 0 answers at once) for it to finish. Free.
func (s *EmailService) GetVerification(ctx context.Context, verificationID string, wait int) (*VerifyResponse, error) {
	// The API's mailbox-check IDs are UUIDs; anything else could reach another path.
	if !uuidPattern.MatchString(verificationID) {
		return nil, fmt.Errorf("touchmark: verificationID must be a UUID, not %q", verificationID)
	}
	query := url.Values{"wait": {strconv.Itoa(wait)}}
	var answer VerifyResponse
	return &answer, s.c.send(ctx, http.MethodGet, "/v1/email/verify/"+verificationID+"?"+query.Encode(), nil, "", &answer)
}

// WaitForVerification polls a mailbox check until it is done or timeout
// passes, and returns the last answer. Free.
func (s *EmailService) WaitForVerification(ctx context.Context, verificationID string, timeout time.Duration) (*VerifyResponse, error) {
	deadline := time.Now().Add(timeout)
	for {
		left := int(math.Ceil(time.Until(deadline).Seconds()))
		wait := MaxWaitSeconds
		if left < wait {
			wait = left
		}
		if wait < 0 {
			wait = 0
		}
		answer, err := s.GetVerification(ctx, verificationID, wait)
		if err != nil || answer.Status == "done" || !time.Now().Before(deadline) {
			return answer, err
		}
	}
}

// DomainService holds the domain calls.
type DomainService struct{ c *Client }

// SenderReadiness checks a domain's DNS against the Gmail, Yahoo and Microsoft sender rules. 2 credits.
func (s *DomainService) SenderReadiness(ctx context.Context, body SenderReadinessRequest, options ...CallOption) (*SenderReadinessResponse, error) {
	var answer SenderReadinessResponse
	return &answer, s.c.post(ctx, "/v1/domain/sender-readiness", body, &answer, options)
}

// IPService holds the IP calls.
type IPService struct{ c *Client }

// Lookup gives an address's country, network owner, hosting company and Tor exit. 1 credit.
func (s *IPService) Lookup(ctx context.Context, body LookupRequest, options ...CallOption) (*LookupResponse, error) {
	var answer LookupResponse
	return &answer, s.c.post(ctx, "/v1/ip/lookup", body, &answer, options)
}

// LookupBatch looks up to 100 addresses, answered in order. 1 credit each.
func (s *IPService) LookupBatch(ctx context.Context, body BatchLookupRequest, options ...CallOption) (*BatchLookupResponse, error) {
	var answer BatchLookupResponse
	return &answer, s.c.post(ctx, "/v1/ip/lookup/batch", body, &answer, options)
}

// PhoneService holds the phone calls.
type PhoneService struct{ c *Client }

// Validate checks numbering-plan validity, formats, country and line type. 1 credit.
func (s *PhoneService) Validate(ctx context.Context, body PhoneValidateRequest, options ...CallOption) (*PhoneValidateResponse, error) {
	var answer PhoneValidateResponse
	return &answer, s.c.post(ctx, "/v1/phone/validate", body, &answer, options)
}

// ValidateBatch validates up to 100 numbers, answered in order. 1 credit each.
func (s *PhoneService) ValidateBatch(ctx context.Context, body PhoneBatchValidateRequest, options ...CallOption) (*PhoneBatchValidateResponse, error) {
	var answer PhoneBatchValidateResponse
	return &answer, s.c.post(ctx, "/v1/phone/validate/batch", body, &answer, options)
}

// AccountService holds the account call.
type AccountService struct{ c *Client }

// Get reads the credit balance, the tier and the key. Free.
func (s *AccountService) Get(ctx context.Context) (*AccountResponse, error) {
	var answer AccountResponse
	return &answer, s.c.send(ctx, http.MethodGet, "/v1/account", nil, "", &answer)
}

// post sends a charged call: its body and Idempotency-Key stay the same on
// every retry, so the API charges it at most once.
func (c *Client) post(ctx context.Context, path string, body any, answer any, options []CallOption) error {
	var o callOptions
	for _, option := range options {
		option(&o)
	}
	if o.idempotencyKey == "" {
		o.idempotencyKey = newUUID()
	}
	payload, err := json.Marshal(body)
	if err != nil {
		return err
	}
	return c.send(ctx, http.MethodPost, path, payload, o.idempotencyKey, answer)
}

func (c *Client) send(ctx context.Context, method, path string, payload []byte, idempotencyKey string, answer any) error {
	for attempt := 0; ; attempt++ {
		err := c.once(ctx, method, path, payload, idempotencyKey, answer)
		var stop final
		if errors.As(err, &stop) {
			return stop.error
		}
		if err == nil || ctx.Err() != nil || attempt >= c.maxRetries {
			return err
		}
		delay := time.Duration(attempt+1) * time.Second
		var apiErr *Error
		if errors.As(err, &apiErr) {
			if !retryable(apiErr) {
				return err
			}
			if apiErr.RetryAfter >= 0 {
				delay = apiErr.RetryAfter
			}
		}
		if delay > maxRetryDelay {
			delay = maxRetryDelay
		}
		if err := c.sleep(ctx, delay); err != nil {
			return err
		}
	}
}

func (c *Client) once(ctx context.Context, method, path string, payload []byte, idempotencyKey string, answer any) error {
	var body io.Reader
	if payload != nil {
		body = bytes.NewReader(payload)
	}
	request, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, body)
	if err != nil {
		return err
	}
	request.Header.Set("Authorization", "Bearer "+c.apiKey)
	request.Header.Set("Accept", "application/json")
	request.Header.Set("User-Agent", userAgent)
	if payload != nil {
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	response, err := c.http.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	data, err := io.ReadAll(response.Body)
	if err != nil {
		return err
	}
	if response.StatusCode < 200 || response.StatusCode > 299 {
		return toError(response, data)
	}
	if err := json.Unmarshal(data, answer); err != nil {
		return final{fmt.Errorf("touchmark: reading the answer: %w", err)}
	}
	return nil
}

// final wraps an error that a retry cannot fix.
type final struct{ error }

func (f final) Unwrap() error { return f.error }

func retryable(err *Error) bool {
	switch err.Status {
	case 429, 500, 502, 503, 504:
		return true
	case 409:
		return err.Code == "idempotency_key_in_use"
	}
	return false
}

func toError(response *http.Response, data []byte) *Error {
	var problem struct {
		Code   *string `json:"code"`
		Detail *string `json:"detail"`
	}
	_ = json.Unmarshal(data, &problem) // not a problem document: a proxy's page, for example
	err := &Error{
		Status:     response.StatusCode,
		Code:       fmt.Sprintf("http_%d", response.StatusCode),
		RequestID:  response.Header.Get("X-Request-Id"),
		RetryAfter: -1,
	}
	if problem.Code != nil {
		err.Code = *problem.Code
	}
	if problem.Detail != nil {
		err.Detail = *problem.Detail
	}
	if seconds, parseErr := strconv.ParseFloat(response.Header.Get("Retry-After"), 64); parseErr == nil &&
		seconds >= 0 && !math.IsInf(seconds, 0) {
		err.RetryAfter = time.Duration(seconds * float64(time.Second))
	}
	return err
}

func newUUID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err) // crypto/rand does not fail on supported platforms
	}
	b[6] = b[6]&0x0f | 0x40
	b[8] = b[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

func sleep(ctx context.Context, d time.Duration) error {
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
