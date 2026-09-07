# Operations guide

## Starting a demo

Start the backend and frontend as described in [SETUP.md](SETUP.md), open the dashboard, and press `Play Stream`.

The simulator is paused at startup. Use the speed buttons to move through the sample timeline. `100x` is useful for a quick demonstration; lower speeds make debounce behaviour easier to observe.

## Reading the dashboard

- **Workload** contains Actionable threads.
- **Informational** contains messages that can normally be archived.
- **Irrelevant** contains messages retained for review.
- The department selector changes the current view.

Open a thread to see its summary, entities, actions, rationales, confidence, notes, drafts, audit history, and Q&A.

Sign in with one of the development users listed in [SETUP.md](SETUP.md). The department selector is limited by the authenticated user's department scope.

## Handler controls

Actions can be checked to mark them resolved or edited with `Edit`. Internal notes are private operational context within the current prototype. Draft text must be reviewed before it is approved.

A human triage override requires a reason. The override is visible in the thread and recorded in the audit history.

## Debounce controls

The top control strip exposes the debounce toggle and Broker window. The API supports all source categories:

```text
GET   /api/debounce-settings
PATCH /api/debounce-settings
GET   /api/debounce-analytics
POST  /api/debounce-settings/apply-analytics
```

`Apply analytics` uses observed follow-up intervals from `artifacts/analytics/raw_followup_data.csv`. It updates runtime settings only; it is not a long-term configuration store.

## Provider usage

The backend applies a shared concurrency and pacing guard to model calls. Current in-process usage can be inspected at:

```text
GET http://localhost:8000/api/provider-metrics
```

The response includes request counts, failures, elapsed time, token usage when available, estimated cost, and operation-level totals. Metrics reset when the backend restarts.

Pending follow-up debounce batches are stored in SQLite with their due time and source message IDs. If the backend restarts during a debounce window, the orchestrator restores the pending batch and schedules it for the remaining time.

On a normal shutdown, the backend cancels timer handles and flushes buffered batches before exiting. Allow the shutdown to complete rather than terminating the process forcefully if preserving the latest batch matters.

## Resetting a demonstration

Stop the backend and remove `backend/triage_state.db`. Restart both services, then press `Play Stream`. Do not delete the source JSON.

## Common issues

### The dashboard is empty

Confirm the backend is running on port 8000, the frontend is running on port 5173, and `Play Stream` has been pressed.

### A department is empty

Allow the simulator to process more messages or check the central routing result. The department selector filters already processed threads; it does not trigger processing for that department.

### A thread is rejected as outside the handler scope

Select the department shown by the thread's `handler_type`. API clients must send the matching `X-Handler-Type` header.

### Old duplicate actions remain visible

Restart the backend after code changes. Legacy actions are normalised when read. A full reset gives the cleanest demonstration.
