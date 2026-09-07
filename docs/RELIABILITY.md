# Reliability design

This document explains how the prototype protects model calls and why the controls are deliberately limited.

## Trace IDs and prompt versions

Each triage run receives a UUID in the orchestrator before entering LangGraph. The graph includes that ID in its audit events, alongside the prompt version and model name. See [orchestrator.py](../backend/src/services/orchestrator.py#L174) and [nodes.py](../backend/src/llm/nodes.py#L20).

The prompt version is currently `triage-v1`. Changing a prompt should produce a new version so later audit records can be compared with earlier decisions.

Provider metrics also create a trace ID for each provider operation. The metrics are held in memory and are intended for local diagnosis, not as a substitute for a durable tracing system.

## Backpressure

All synchronous and asynchronous model calls pass through `ProviderBackpressure` in [provider.py](../backend/src/core/provider.py#L114). It limits concurrent calls with semaphores and spaces requests by a minimum interval. A saturated synchronous slot raises a timeout rather than allowing unlimited work to accumulate.

The triage nodes use the guard at the classifier, extraction, scoring, and consolidation calls. Q&A and drafting use it in [routes.py](../backend/src/api/routes.py#L349) and [routes.py](../backend/src/api/routes.py#L444).

This is an in-process control. A multi-worker deployment would need a shared rate limiter or provider gateway.

## Model fallback

Triage uses GPT-4o-mini as the primary model and GPT-4o as its structured-output fallback. The fallback chain is constructed for each triage stage in [nodes.py](../backend/src/llm/nodes.py#L67-L107). Q&A and drafting use GPT-4o first and GPT-4o-mini as the fallback in [routes.py](../backend/src/api/routes.py#L339-L384) and [routes.py](../backend/src/api/routes.py#L433).

A fallback is not a silent policy change: the operation and configured primary model remain visible in provider metrics, while the audit trail records the triage model configuration. A production implementation should also record the model actually selected by the provider callback and alert on fallback frequency.

## Caching

The cache is implemented in [provider.py](../backend/src/core/provider.py#L81-L112). It is an in-memory TTL cache with a 30-second lifetime. Keys are SHA-256 hashes of the operation and relevant inputs; the raw email text is not used as a cache key or returned by the cache API.

Only Q&A and draft generation use caching:

- Q&A keys include the question, thread scope, and each thread's `last_updated` value in [routes.py](../backend/src/api/routes.py#L434).
- Draft keys include thread ID, draft type, summary, and unresolved actions in [routes.py](../backend/src/api/routes.py#L349).
- Triage calls are deliberately not cached because follow-up messages, action resolution, human overrides, and notes can change the correct result.

The thread timestamp changes when a handler mutates actions, notes, or triage, which naturally invalidates the related Q&A key. Cache hits are counted in provider metrics.

Caching is not a correctness guarantee. It reduces repeated requests for identical short-lived reads; it must not be used to bypass access checks or approval controls.

## Uniform model-call contract

Every model-facing workflow should follow the same contract:

1. Create a trace ID and prompt version.
2. Detect and pseudonymise PII locally.
3. Build a versioned prompt from the redacted content.
4. Call the provider through backpressure, fallback, and metrics.
5. Validate the structured response.
6. Reinject only known local tokens after validation and authorisation.
7. Persist the decision without persisting the raw prompt or replacement map in telemetry.

The current code has the provider guard, prompt versions, trace IDs, structured outputs, and the initial email/phone redaction boundary. Full reversible pseudonymisation and token reinjection remain a documented production requirement rather than an implemented capability.

Prompt-injection handling is an additional boundary: [prompt_safety.py](../backend/src/core/prompt_safety.py#L1-L18) marks common instruction-like phrases in email content before the text enters a model prompt. This complements, but does not replace, structured outputs, source grounding, model instructions, and human approval.

## Token and cost metrics

`ProviderMetrics` records elapsed time, usage metadata when supplied by the provider, success/failure, operation, trace ID, and an estimated cost in [provider.py](../backend/src/core/provider.py#L28-L78). The dashboard/API can inspect the aggregate through `GET /api/provider-metrics`, implemented in [routes.py](../backend/src/api/routes.py#L462).

The estimate is illustrative and model pricing must be reviewed before operational use. Metrics reset when the process restarts.

## Langfuse observability

When `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are configured, [observability.py](../backend/src/core/observability.py#L1-L48) sends trace metadata for provider operations to Langfuse. The integration is optional and fail-safe: telemetry errors do not stop triage.

The trace contains the operation, model name, trace ID, cache status, elapsed time, success state, token usage, and estimated cost when the provider exposes usage metadata. It deliberately sends `{"redacted": true}` rather than prompt text, email bodies, replacement maps, or credentials. The provider boundary invokes it from [provider.py](../backend/src/core/provider.py#L28-L88).

Supervisors, auditors, admins, and platform admins may see observability status through `GET /api/observability/status`. Direct Langfuse project access should be managed separately with Langfuse roles; normal handlers should not receive unrestricted trace access.

## What this does not solve

These controls do not provide distributed rate limiting, durable metrics, guaranteed retries, circuit breaking, or complete provider observability. Those belong in the production architecture alongside identity, queues, and a proper telemetry system.

The deterministic policy guardrails are implemented after model interpretation in [nodes.py](../backend/src/llm/nodes.py#L28-L70). They clear actions from Irrelevant classifications and apply minimum priority floors for high-importance, legal, safety, theft, and uninhabitable signals. Guardrail interventions are written to the audit trail and reduce calibrated confidence to encourage human review.
