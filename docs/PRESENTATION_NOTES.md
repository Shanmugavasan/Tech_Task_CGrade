# Presentation notes

## The problem

Operational handlers receive a mixture of customer, broker, internal, and automated emails. The difficult part is not simply reading them faster; it is deciding which messages require action, what that action is, and what should happen first.

## The proposed approach

The prototype treats the mailbox as a stream of threads. It centralises ingestion, assigns a department, waits briefly for likely follow-ups, and sends a structured view of the thread through a triage graph. The handler sees a ranked workload rather than an undifferentiated inbox.

## Architecture decisions

- LangGraph makes the triage stages explicit and auditable.
- GPT-4o-mini is used for high-volume triage; GPT-4o is used for interactive Q&A and drafting.
- SQLite keeps the demonstration self-contained while retaining source messages and decisions.
- REST provides hydration and mutations; WebSockets provide live updates.
- Human approval is required for generated text and human overrides require a reason.

## Demo sequence

1. Start with the simulator paused.
2. Explain the department selector: it changes the view, not ingestion.
3. Play the stream at high speed to populate the dashboard.
4. Open a High priority Actionable thread.
5. Show the rationale, confidence, actions, and audit history.
6. Resolve or edit an action and add an internal note.
7. Generate a reply suggestion and show that it remains pending until approved.
8. Ask a question and point to the source message references.
9. Open the Informational and Irrelevant views.
10. Show debounce settings and the analytics recommendation action.

## Evaluation

The repository includes a small labelled smoke evaluation for classification and priority. Results report coverage separately from accuracy. The evaluation is deliberately modest and is presented as evidence of a repeatable process, not as a production benchmark.

## Assumptions

- The handler is responsible for one or more operational departments.
- A thread is the right unit for triage rather than an isolated message.
- Follow-up bursts should usually be consolidated.
- AI suggestions require human review.
- The simulator is sufficient to demonstrate the workflow before mailbox integration.

## Limitations and next steps

The prototype does not connect to an inbox, provide real authentication, or implement the production queue and resilience layer. The next production steps are identity integration, durable ingestion, bounded concurrency, GDPR controls, observability, and a larger expert-labelled evaluation set.
