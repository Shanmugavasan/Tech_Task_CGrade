# Features

## Thread classification

Each thread is classified as one of:

- **Actionable** - a handler needs to review, decide, verify, contact someone, or complete a task.
- **Informational** - useful context or an update that normally does not require work.
- **Irrelevant** - outside the handler's workload, such as marketing or a misdirected message.

Informational and Irrelevant threads remain available for review. They are not counted as workload items.

## Priority

Actionable threads receive a score from 0 to 100 and a level:

- High: 80-100
- Medium: 40-79
- Low: 0-39

The scorer considers urgency, business impact, the extracted work, and the source email's importance flag. A high importance flag cannot leave a message in Low priority, but it does not automatically make every message High.

## Department views

The system routes each thread to Claims, Motor, Home, Liability, or Finance. The handler selector changes the visible department and is not an ingestion control.

## Actions

Tasks have stable IDs and can be:

- Marked resolved or reopened.
- Edited by a handler.
- Consolidated when follow-up messages repeat the same work.
- Retained with their deadline and resolution state.

Human changes are persisted in the thread state.

## Explanations and confidence

The detail panel shows the classification rationale, priority rationale, and confidence values for classification, extraction, and prioritisation. Extraction and priority are shown as not applicable for non-actionable messages because those stages are intentionally skipped.

The calibrated confidence signal also considers evidence completeness and deterministic policy guardrails; it is not simply the model's self-reported confidence.

## Audit history

Each triage run records its graph stages, source message ID, model, prompt version, time, and decision metadata. Human overrides are recorded as separate audit events.

## Internal notes

Handlers can add and delete notes on a thread. Notes are separate from AI-generated actions and are stored with the thread.

## Suggested text

The system can produce two kinds of drafts:

- External reply
- Internal handler note

Drafts are editable and have Pending, Approved, or Rejected status. Approval is a review state only. The prototype does not send email.

## Questions and sources

Q&A retrieves relevant persisted source messages, combines them with thread summaries, and asks GPT-4o to answer from that context. Responses include the source thread and message IDs used for retrieval.

## Debounce

The runtime policy can be enabled or disabled. Current source defaults are:

- Customer: 2 minutes
- Internal: 2 minutes
- Broker: 5 minutes
- Automated: 10 minutes

The window is adjusted by simulator speed. Follow-up analytics can produce bounded recommendations and apply them to the live settings.
