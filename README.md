# Aviva Email Triage Engine

This project is a working prototype for helping insurance operations handlers make sense of a busy mailbox. It ingests a time-scaled stream of sample emails, groups related messages into threads, assigns each thread to a handler department, and uses an LLM-assisted workflow to identify what needs attention.

The dashboard is intended to answer a practical question: "What needs my attention now, and why?"

## What it does

- Classifies threads as Actionable, Informational, or Irrelevant.
- Extracts policy references, people, organisations, third parties, tasks, and deadlines.
- Scores urgency and business impact from 0 to 100 and assigns High, Medium, or Low priority.
- Routes threads centrally to Claims, Motor, Home, Liability, or Finance.
- Groups follow-ups using source-specific debounce windows.
- Shows rationale, confidence, audit history, original message sources, and outstanding actions.
- Allows handlers to resolve or edit actions, add internal notes, and override AI decisions with a recorded reason.
- Generates editable external-reply and internal-note suggestions that require human approval.
- Answers questions using retrieved original email messages and returns source references.
- Uses observed follow-up analytics to recommend debounce settings.

## Architecture at a glance

The backend is a FastAPI application. A simulator currently stands in for a mailbox and emits 95 sample messages across 50 threads. LangGraph coordinates the triage stages, SQLite stores thread state, source messages, audit events, and drafts, and WebSockets push state changes to the React dashboard.

The simulator is deliberately local. This submission does not connect to Microsoft Graph, Outlook, or a live inbox.

## Project structure

- `backend/` - FastAPI application, ingestion simulator, LangGraph workflow, persistence, and evaluation script.
- `frontend/` - React and Vite handler dashboard.
- `artifacts/` - Analytics outputs, evaluation results, and test reports.
- `docs/` - Setup, architecture, feature, API, operations, evaluation, reliability, security, and presentation documentation.

## Running the project

Start with [docs/SETUP.md](docs/SETUP.md). The shorter operational instructions are in [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Important limitations

This is a prototype rather than a production mailbox service. It has no real inbox connector, durable queue, corporate identity integration, vector database, automatic email sending, or complete GDPR control set. It does include a development login/session flow, role and department checks, retention/export controls, encryption support, and prompt-safety controls. The remaining boundaries are described in [docs/SECURITY_AND_LIMITATIONS.md](docs/SECURITY_AND_LIMITATIONS.md).

The provider reliability controls, including backpressure, fallback models, trace IDs, caching, and usage metrics, are described in [docs/RELIABILITY.md](docs/RELIABILITY.md).# Tech_Task_CGrade
