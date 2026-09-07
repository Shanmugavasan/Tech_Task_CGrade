import asyncio
import csv
import uuid
from pathlib import Path
from typing import Dict
from datetime import datetime, timedelta, timezone

from src.ingestion.simulator import MockStreamEmailSource
from src.core.database import (
    get_thread_messages,
    get_messages_by_ids,
    get_pending_debounces,
    delete_pending_debounce,
    save_pending_debounce,
    get_thread_state,
    save_audit_events,
    save_messages,
    save_thread_state,
)
from src.core.models import ThreadState, EmailMessage, LLMTriageOutput
from src.api.websockets import manager
from src.llm.graph import triage_pipeline

# Initialize the global simulator instance
simulator = MockStreamEmailSource(filepath="data/emails_candidate.json", speed_multiplier=1.0)
HANDLER_TYPES = {
    "Claims": "General claims handling and customer action",
    "Motor": "Motor claims, repairers, recovery, and vehicle assessment",
    "Home": "Home claims, property damage, and emergency assistance",
    "Liability": "Liability claims, legal correspondence, and evidence",
    "Finance": "Invoices, payments, authority, and supplier follow-up",
}

# In-memory buffer to track active debounce timers by thread_id
_debounce_timers: Dict[str, asyncio.TimerHandle] = {}
_pending_messages: Dict[str, list[EmailMessage]] = {}

DEBOUNCE_SETTINGS_MINUTES = {
    "Customer": 2.0,
    "Internal": 2.0,
    "Broker": 5.0,
    "Automated": 10.0,
}
debounce_enabled = True


def _source_from_sender(sender: str) -> str:
    sender = sender.lower()
    if sender.startswith("no-reply") or sender.startswith("noreply") or any(
        term in sender for term in ("notification", "alerts", "automated", "system")
    ):
        return "Automated"
    if any(term in sender for term in ("broker", "broking", "brokers")):
        return "Broker"
    if "pinnacle-insurance.co.uk" in sender:
        return "Internal"
    return "Customer"


def get_analytics_recommendations() -> dict[str, dict]:
    """Reads observed follow-up intervals and derives bounded source windows."""
    analytics_path = Path(__file__).resolve().parents[3] / "artifacts" / "analytics" / "raw_followup_data.csv"
    intervals: dict[str, list[float]] = {source: [] for source in DEBOUNCE_SETTINGS_MINUTES}
    if analytics_path.exists():
        with analytics_path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                value = row.get("time_since_last_msg_mins")
                if not value:
                    continue
                intervals[_source_from_sender(row.get("sent_from", ""))].append(float(value))

    recommendations = {}
    for source, values in intervals.items():
        if values:
            values.sort()
            median = values[len(values) // 2]
            recommended = round(max(2.0, min(15.0, median / 2)), 1)
        else:
            median = None
            recommended = DEBOUNCE_SETTINGS_MINUTES[source]
        recommendations[source] = {
            "sample_count": len(values),
            "median_followup_minutes": median,
            "recommended_debounce_minutes": recommended,
        }
    return recommendations


def apply_analytics_recommendations() -> dict[str, dict]:
    recommendations = get_analytics_recommendations()
    for source, recommendation in recommendations.items():
        DEBOUNCE_SETTINGS_MINUTES[source] = recommendation["recommended_debounce_minutes"]
    return recommendations


def infer_email_source(message: EmailMessage) -> str:
    """Classifies the sender category used by debounce policy."""
    sender = str(message.sent_from).lower()
    subject_body = f"{message.subject} {message.body}".lower()
    if sender.startswith("no-reply") or sender.startswith("noreply") or any(
        term in sender for term in ("notification", "alerts", "automated", "system")
    ):
        return "Automated"
    if any(term in sender for term in ("broker", "broking", "brokers")) or "broker" in subject_body:
        return "Broker"
    if "pinnacle-insurance.co.uk" in sender or sender.endswith("@pinnacle-insurance.co.uk"):
        return "Internal"
    return "Customer"


def get_debounce_minutes(message: EmailMessage) -> float:
    return DEBOUNCE_SETTINGS_MINUTES[infer_email_source(message)]


def update_debounce_settings(
    enabled: bool | None = None,
    source: str | None = None,
    minutes: float | None = None,
) -> None:
    global debounce_enabled
    if enabled is not None:
        debounce_enabled = enabled
    if source is not None and minutes is not None:
        DEBOUNCE_SETTINGS_MINUTES[source] = minutes


def is_debounce_enabled() -> bool:
    return debounce_enabled


def infer_handler_type(messages: list[EmailMessage]) -> str:
    """Routes a thread centrally; the UI selection must not control ingestion."""
    text = " ".join(
        " ".join([
            message.subject,
            message.body,
            str(message.sent_from),
            " ".join(str(address) for address in message.sent_to),
            " ".join(str(address) for address in (message.sent_cc or [])),
        ])
        for message in messages
    ).lower()

    department_terms = {
        "Motor": ("motor", "vehicle", "bodyshop", "garage", "repairer", "car ", "van "),
        "Home": ("home", "property", "roof", "storm damage", "escape of water", "tenant"),
        "Liability": ("liability", "solicitor", "injury", "slip-and-fall", "physio", "legal"),
        "Finance": ("finance", "invoice", "payment", "accounts", "supplier", "storage charges"),
    }
    scores = {
        handler_type: sum(text.count(term) for term in terms)
        for handler_type, terms in department_terms.items()
    }
    best_handler, best_score = max(scores.items(), key=lambda item: item[1])
    return best_handler if best_score else "Claims"

async def process_thread_batch(thread_id: str):
    """Fires when a new thread arrives or a debounce timer expires."""
    messages = _pending_messages.pop(thread_id, [])
    if not messages:
        return

    delete_pending_debounce(thread_id)

    save_messages(messages)

    # Check if thread already exists in the database
    existing_state = get_thread_state(thread_id)
    persisted_messages = get_thread_messages(thread_id)
    
    # Prepare the LangGraph state input
    selected_handler_type = existing_state.handler_type if existing_state else infer_handler_type(messages)
    input_state = {
        "trace_id": str(uuid.uuid4()),
        "current_message": messages[-1], # The latest message drives the current action
        "handler_type": selected_handler_type,
        "existing_messages": persisted_messages[:-1],
        "audit_trail": []
    }

    if existing_state:
        input_state["thread_summary"] = existing_state.current_triage.one_line_summary
        input_state["existing_actions"] = existing_state.current_triage.required_actions
        # Note: In a production system, we would inject all past context here

    # Run the LangGraph Triage Pipeline asynchronously
    print(f"[Orchestrator] Processing thread {thread_id} through LLM Graph...")
    result_state = await triage_pipeline.ainvoke(input_state)
    save_audit_events(thread_id, result_state.get("audit_trail", []))

    # Reconstruct the strict output schema
    triage_output = LLMTriageOutput(
        classification=result_state.get("classification", "Irrelevant"),
        classification_reasoning=result_state.get("classification_reasoning", ""),
        classification_confidence=result_state.get("classification_confidence", 0.0),
        calibrated_confidence=result_state.get("calibrated_confidence", result_state.get("classification_confidence", 0.0)),
        priority_score=result_state.get("priority_score", 0),
        priority_level=result_state.get("priority_level", "Low"),
        urgency_justification=result_state.get("urgency_justification", ""),
        priority_confidence=result_state.get("priority_confidence", 0.0),
        entities=result_state.get("entities", {"third_parties": []}),
        required_actions=result_state.get("existing_actions", []),
        extraction_confidence=result_state.get("extraction_confidence", 0.0),
        classification_source="ai",
        priority_source="ai",
        override_reason="",
        one_line_summary=result_state.get("thread_summary", "No summary available.")
    )

    # Save to SQLite
    try:
        new_thread_state = ThreadState(
            thread_id=thread_id,
            handler_type=selected_handler_type,
            last_updated=datetime.now(),
            message_count=(existing_state.message_count if existing_state else 0) + len(messages),
            current_triage=triage_output,
            internal_notes=existing_state.internal_notes if existing_state else []
        )
    except Exception as e:
        print(f"[Orchestrator] ERROR building ThreadState: {e}")
        return
    save_thread_state(new_thread_state)

    # Push real-time update to the React Dashboard
    await manager.broadcast_state({
        **new_thread_state.model_dump(mode="json"),
        "current_simulation_time": messages[-1].date_sent.isoformat()
    })
    print(f"[Orchestrator] Thread {thread_id} updated and broadcasted to UI.")

async def start_ingestion_loop():
    """Background task that pulls from the simulator and applies debounce logic."""
    await simulator.connect()
    print("[Orchestrator] Starting asynchronous ingestion loop...")
    
    loop = asyncio.get_running_loop()

    for pending in get_pending_debounces():
        restored_messages = get_messages_by_ids(pending["message_ids"])
        if not restored_messages:
            delete_pending_debounce(pending["thread_id"])
            continue
        _pending_messages[pending["thread_id"]] = restored_messages
        delay = max(0.0, (pending["due_at"] - datetime.now(timezone.utc)).total_seconds())
        _debounce_timers[pending["thread_id"]] = loop.call_later(
            delay,
            lambda t_id=pending["thread_id"]: asyncio.create_task(process_thread_batch(t_id)),
        )

    async for msg in simulator.stream_emails():
        thread_id = msg.thread_id
        
        # Append message to pending buffer
        if thread_id not in _pending_messages:
            _pending_messages[thread_id] = []
        _pending_messages[thread_id].append(msg)

        existing_state = get_thread_state(thread_id)

        # 1. New Thread: Process immediately (Bypass debounce)
        if not existing_state:
            await process_thread_batch(thread_id)
            continue

        # 2. Existing Thread: Apply the configured source-specific debounce
        if not debounce_enabled:
            await process_thread_batch(thread_id)
            continue

        # Cancel the existing timer if it's currently ticking
        if thread_id in _debounce_timers:
            _debounce_timers[thread_id].cancel()
        
        # Calculate delay based on simulation speed (e.g., 2 mins / 10x speed = 12 seconds)
        actual_delay_seconds = get_debounce_minutes(msg) * 60 / simulator.speed_multiplier
        
        # Schedule the batch to process after the debounce window
        _debounce_timers[thread_id] = loop.call_later(
            actual_delay_seconds, 
            lambda t_id=thread_id: asyncio.create_task(process_thread_batch(t_id))
        )
        save_pending_debounce(
            thread_id,
            datetime.now(timezone.utc) + timedelta(seconds=actual_delay_seconds),
            _pending_messages[thread_id],
        )


async def shutdown_ingestion() -> None:
    """Cancel timers and flush buffered messages before the process exits."""
    for timer in _debounce_timers.values():
        timer.cancel()
    _debounce_timers.clear()

    pending_thread_ids = list(_pending_messages)
    if pending_thread_ids:
        await asyncio.gather(
            *(process_thread_batch(thread_id) for thread_id in pending_thread_ids),
            return_exceptions=True,
        )