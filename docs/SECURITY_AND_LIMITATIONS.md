# Security and limitations

This document is intentionally direct about what the prototype provides and where production controls are still required.

## Current controls

- REST and WebSocket boundaries support bearer-token authentication through `AUTH_TOKEN`.
- The browser has a login screen backed by session cookies; the seeded accounts are development-only.
- Users can be mapped from `AUTH_USERS_JSON` to a user ID, role, and department set.
- Handler, supervisor, auditor, and admin roles have different mutation permissions.
- Handler scope is checked using the `X-Handler-Type` request header.
- Draft approval is separate from sending; the prototype has no send-mail operation.
- Triage decisions and human overrides are recorded in an audit table.
- Source messages are retained so Q&A can refer back to the original material.
- Provider prompts redact email addresses and phone numbers before model calls.
- Administrators can delete all retained data for a thread or run a bounded retention purge.
- Authorised users can export the complete record for a thread within their department scope.
- Request access metadata is persisted for administrator review.
- Sensitive persisted fields can be encrypted with `DATA_ENCRYPTION_KEY`.
- Structured outputs constrain the shape of model responses.
- Prompt instructions tell the Q&A and drafting models not to invent unsupported facts.

## Not production security

When `AUTH_TOKEN` is not configured in development, the prototype uses a local demo user so the interview setup remains simple. When configured, REST and WebSocket requests require the bearer token. The current token mechanism is still a prototype boundary and should be replaced with the organisation's IAM/OIDC provider before deployment.

For a multi-user demonstration, `AUTH_USERS_JSON` can contain records such as:

```json
[
	{
		"token": "local-secret",
		"user_id": "home-handler-1",
		"role": "handler",
		"handler_types": ["Home"]
	}
]
```

The mapping and permission checks live in [security.py](../backend/src/core/security.py#L20-L83). Route-level enforcement is applied in [routes.py](../backend/src/api/routes.py#L50-L60) and on mutation endpoints such as [routes.py](../backend/src/api/routes.py#L204-L215). The caller-supplied department header is only a view selector and must be present in the authenticated user's department set.

The current role policy is:

| Role | Department scope | Typical permissions |
| --- | --- | --- |
| `handler` | Assigned departments | Workload, actions, notes, drafts, and human overrides |
| `supervisor` | Multiple assigned departments | Handler permissions plus debounce and quality administration |
| `auditor` | Assigned departments | Read-only thread, audit, evaluation, and observability access |
| `admin` | All assigned departments | User, retention, export, security, and application administration |
| `platform_admin` | Platform-wide | Full operational and observability administration; use only for break-glass/platform duties |

`platform_admin` automatically satisfies role checks, but it should not be used as a normal daily account. Production access should require MFA, stronger approval, and enhanced audit logging.

Retention is explicit rather than silent. `DELETE /api/threads/{thread_id}/data` removes the thread, source messages, audit events, drafts, and pending debounce records. `POST /api/admin/retention/purge` removes threads older than the configured number of days and is restricted to administrators. The implementation is in [database.py](../backend/src/core/database.py#L260-L310) and [routes.py](../backend/src/api/routes.py#L160-L180).

`GET /api/threads/{thread_id}/export` provides a JSON export of the authorised thread state, source messages, notes, audit history, and drafts. It reuses the same department-scope check as normal thread access and is implemented in [routes.py](../backend/src/api/routes.py#L155-L170).

The HTTP middleware in [main.py](../backend/main.py#L35-L55) records access events in SQLite. It deliberately excludes credentials, request bodies, and message content. Administrators can read the recent records through `/api/admin/access-log`. A production deployment should add retention for access logs, tamper-evident storage, and centralised SIEM forwarding.

The browser login and session endpoints are implemented in [security.py](../backend/src/core/security.py#L130-L177). Sessions are HttpOnly cookies with an eight-hour prototype lifetime and are held in process memory, so restarting the backend logs users out. This is suitable for a demonstration, not a horizontally scaled service.

The handler scope header is not itself authentication. In the next security layer it should be derived from authenticated user claims rather than trusted as a caller-supplied value.

The prototype still requires production hardening in these areas:

- Corporate IAM/OIDC integration instead of seeded users and in-process sessions.
- Shared session storage for multiple backend workers.
- Full database encryption and encrypted backups.
- Enterprise PII detection for names, addresses, policy references, and free-form sensitive content.
- Centralised, tamper-evident access-log retention and SIEM forwarding.
- Distributed rate limiting, retries, circuit breaking, and durable metrics.
- Durable queues and worker processes for real mailbox volumes.
- A live mailbox connector.

## Data handling

The sample data contains realistic insurance-style personal information, including names, email addresses, phone numbers, policy references, and legal or claims context. It is suitable for local demonstration only. A real deployment would need a documented legal basis, data minimisation, retention policy, access controls, and an approved provider/data-processing arrangement.

Never commit `backend/.env` or a real API key. Use local environment injection and rotate any key that has been exposed.

The model boundary uses [pii.py](../backend/src/core/pii.py#L1-L20) to redact email addresses and phone numbers in triage, thread-history, and Q&A prompt context. Original messages remain in local SQLite so source references and audit review still work. This is a first minimisation layer, not complete PII detection: names, policy references, addresses, and free-form sensitive content require a stronger enterprise detector and formal retention controls.

## Encryption at rest

When `DATA_ENCRYPTION_KEY` is configured, new thread state, internal notes, message subjects/bodies/senders, draft bodies, and audit decision details are encrypted with Fernet before being written to SQLite. The implementation is in [crypto.py](../backend/src/core/crypto.py#L1-L30) and is applied by [database.py](../backend/src/core/database.py#L135-L230). Existing plaintext rows remain readable to support migration; they are not automatically rewritten until the record is saved again. Losing the key makes encrypted records unrecoverable, so the key must be stored in a proper secret manager and backed up under controlled access.

SQLite itself is not encrypted by this layer. Production deployment should use encrypted storage or SQLCipher, protected backups, filesystem permissions, and TLS for network connections.

## Pseudonymisation design

The intended production flow is:

```text
original message
		-> detect PII locally
		-> replace values with request-scoped tokens
		-> send only tokenised content to the model
		-> validate structured model output
		-> restore known tokens locally for the authorised user
		-> return the result to the API or UI
```

For example, a local redaction context would hold:

```json
{
	"redacted_text": "[PERSON_1] called from [EMAIL_1] on [PHONE_1]",
	"replacements": {
		"[PERSON_1]": "Jane Smith",
		"[EMAIL_1]": "jane@example.com",
		"[PHONE_1]": "07700 900123"
	}
}
```

The replacement map must remain local and must never be included in the model prompt, cache key, audit event, or telemetry payload. Reinjection is a local substitution step performed only after the model response has passed schema validation and only for an authenticated user authorised to see the source thread. Unknown tokens or newly invented personal data should not be silently restored; they should remain flagged for review.

The current prototype implements only the first stage of this design: email and phone redaction in [pii.py](../backend/src/core/pii.py#L1-L20). It does not yet detect names or maintain a reversible replacement map, so there is currently no token reinjection step. This distinction is intentional and should be closed before sending real customer data to an external model.

## Human oversight

AI output is decision support. Handlers remain responsible for classification corrections, priority overrides, action completion, and approval of generated text. The system should not make or communicate coverage decisions without appropriate human review.

## Prompt and email risks

Email content is untrusted input. A production implementation should add prompt-injection handling, attachment scanning, content-size limits, sensitive-data controls, and strict separation between instructions and quoted email content.

The current prompt boundary detects common instruction-like phrases such as `ignore previous instructions`, `system message`, and `you are now`, replacing them before model calls in [prompt_safety.py](../backend/src/core/prompt_safety.py#L1-L18). This is a basic defence-in-depth filter, not a complete prompt-injection detector. The model is also instructed to treat email content as data, and generated drafts remain subject to human approval.

The local adversarial smoke cases are in [prompt_injection_cases.json](../backend/data/prompt_injection_cases.json) and are evaluated by [evaluate_prompt_safety.py](../backend/evaluate_prompt_safety.py). The current cases cover instruction override, fake role escalation, automatic approval/send requests, and a normal non-malicious email.

## Production roadmap

Before connecting a real mailbox, add identity and authorization, a durable ingestion queue, bounded model concurrency, retries and dead letters, persistent settings, observability, retention controls, encryption, and a formal evaluation programme.
