# API reference

The API is served from `http://localhost:8000/api`.

## Authentication

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/auth/demo-users` | List development-only seeded users |
| POST | `/auth/login` | Create an HttpOnly session cookie |
| POST | `/auth/logout` | Revoke the current session |
| GET | `/auth/me` | Return the current user and department scope |

The frontend sends the session cookie with `credentials: include`. In production, use an organisation-approved identity provider rather than seeded accounts or in-process sessions.

## Simulation

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/sim/play` | Start the simulator |
| POST | `/sim/pause` | Pause the simulator |
| POST | `/sim/speed` | Set playback multiplier |
| GET | `/handler-types` | List department profiles |
| POST | `/sim/handler-type` | Validate a selected view |

## Threads and source data

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/threads` | List threads in the selected handler scope |
| GET | `/threads/{thread_id}` | Read one thread |
| GET | `/threads/{thread_id}/messages` | Read original messages |
| GET | `/threads/{thread_id}/audit` | Read processing and override history |
| GET | `/threads/{thread_id}/export` | Export the authorised thread record as JSON |

Thread reads use the optional `X-Handler-Type` header. It defaults to `Claims` in the prototype.

When authenticated user mappings are configured, the requested department must be included in that user's `handler_types`. The header does not grant access by itself.

Administrators can remove all retained data for a thread:

```text
DELETE /api/threads/{thread_id}/data
POST   /api/admin/retention/purge?retention_days=365
```

Both operations require the `admin` role. Deletion covers thread state, original messages, audit events, drafts, and pending debounce records.

Administrators can review safe request metadata with:

```text
GET /api/admin/access-log?limit=200
```

The log contains timestamp, user ID, role, method, path, status code, selected department, and client host. It does not contain passwords, bearer tokens, request bodies, or email content.

Thread export uses the caller's authenticated department scope and includes the current thread state, original messages, audit events, internal notes, and reply drafts. It does not bypass access control.

## Actions and notes

| Method | Path | Purpose |
| --- | --- | --- |
| PATCH | `/threads/{thread_id}/actions/{action_id}` | Edit or resolve an action |
| POST | `/threads/{thread_id}/notes` | Add an internal note |
| DELETE | `/threads/{thread_id}/notes/{note_index}` | Delete an internal note |
| PATCH | `/threads/{thread_id}/triage` | Apply a reasoned human override |

A triage override can change classification, priority score, or priority level. The `reason` field is mandatory.

## Drafts

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/threads/{thread_id}/drafts` | List drafts |
| POST | `/threads/{thread_id}/drafts` | Generate an external reply or internal-note draft |
| PATCH | `/drafts/{draft_id}` | Edit or approve/reject a draft |

Draft approval does not send an email.

## Questions

```http
POST /api/qa
Content-Type: application/json

{
  "question": "What action is needed for Broker X?",
  "thread_id": "optional-thread-id"
}
```

The response includes `answer` and a `sources` array containing thread ID, message ID, subject, sender, and timestamp.

Q&A and draft generation use the provider backpressure and short-lived cache described in [RELIABILITY.md](RELIABILITY.md).

## Debounce and analytics

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/debounce-settings` | Read live settings |
| PATCH | `/debounce-settings` | Change toggle or one source window |
| GET | `/debounce-analytics` | Read evidence and recommendations |
| POST | `/debounce-settings/apply-analytics` | Apply recommendations to runtime settings |

Debounce windows are expressed in minutes and are currently limited to 0-60 by the API.

## Provider metrics

```text
GET /provider-metrics
```

The endpoint returns in-process metrics for model calls since the backend started, including request count, successes, failures, elapsed time, token totals when supplied by the provider, estimated cost, and a breakdown by operation. It is intended for local demonstration and is not a durable monitoring store.

```text
GET /observability/status
```

Returns whether the optional Langfuse adapter is enabled. It requires a supervisor, auditor, admin, or platform-admin role.

## WebSocket

The dashboard connects to:

```text
ws://localhost:8000/ws/dashboard
```

Thread state updates are pushed after triage and handler mutations.
