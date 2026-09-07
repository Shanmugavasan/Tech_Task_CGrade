from datetime import datetime, timedelta, timezone
import os
import re
import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.services.orchestrator import (
    DEBOUNCE_SETTINGS_MINUTES,
    HANDLER_TYPES,
    apply_analytics_recommendations,
    get_analytics_recommendations,
    is_debounce_enabled,
    simulator,
    update_debounce_settings,
)
from src.api.websockets import manager
from src.core.database import (
    get_all_threads,
    get_audit_events,
    get_reply_draft,
    get_thread_drafts,
    get_thread_messages,
    get_thread_state,
    get_access_events,
    delete_thread_data,
    purge_threads_older_than,
    save_audit_events,
    save_reply_draft,
    save_thread_state,
)
from src.core.models import ReplyDraft
from src.core.provider import cache_key, provider_backpressure, provider_metrics
from src.core.observability import langfuse_observability
from src.core.pii import redact_message_body, redact_sender
from src.core.prompt_safety import sanitize_untrusted_email
from src.core.security import get_current_user, require_auth, require_handler_scope, require_role

router = APIRouter(prefix="/api", tags=["API"])

class SpeedRequest(BaseModel):
    multiplier: float


class HandlerTypeRequest(BaseModel):
    handler_type: str


class DebounceSettingsRequest(BaseModel):
    enabled: bool | None = None
    source: str | None = None
    debounce_minutes: float | None = None

class QARequest(BaseModel):
    question: str
    thread_id: str | None = None  # optional — scope to one thread


class ActionUpdateRequest(BaseModel):
    task_description: str | None = None
    deadline: datetime | None = None
    is_resolved: bool | None = None


class NoteRequest(BaseModel):
    note: str


class DraftRequest(BaseModel):
    draft_type: str


class DraftUpdateRequest(BaseModel):
    body: str | None = None
    status: str | None = None


class DraftResult(BaseModel):
    body: str


class TriageOverrideRequest(BaseModel):
    classification: str | None = None
    priority_score: int | None = None
    priority_level: str | None = None
    reason: str


def _require_thread_access(state, handler_type: str | None) -> None:
    user = get_current_user()
    requested_handler = handler_type or state.handler_type
    require_handler_scope(requested_handler)
    if state.handler_type != requested_handler:
        raise HTTPException(status_code=403, detail="Thread is outside the handler scope")


def _question_terms(question: str) -> set[str]:
    return {
        term for term in re.findall(r"[a-z0-9]{3,}", question.lower())
        if term not in {"what", "when", "where", "which", "there", "this", "that", "were"}
    }


def _retrieve_messages(threads: list, question: str) -> list[dict]:
    terms = _question_terms(question)
    candidates = []
    for thread in threads:
        for message in get_thread_messages(thread.thread_id):
            searchable = f"{message.subject} {message.body} {message.sent_from}".lower()
            score = sum(searchable.count(term) for term in terms)
            if score > 0:
                candidates.append((score, message))

    candidates.sort(key=lambda item: (item[0], item[1].date_sent), reverse=True)
    selected = candidates[:8]
    return [
        {
            "thread_id": message.thread_id,
            "message_id": message.message_id,
            "subject": message.subject,
            "sent_from": str(message.sent_from),
            "date_sent": message.date_sent.isoformat(),
            "body": message.body,
            "score": score,
        }
        for score, message in selected
    ]

# --- Simulation Controls ---

@router.post("/sim/play")
async def play_simulation():
    simulator.toggle_pause(False)
    return {"status": "playing", "speed": simulator.speed_multiplier}

@router.post("/sim/pause")
async def pause_simulation():
    simulator.toggle_pause(True)
    return {"status": "paused"}

@router.post("/sim/speed")
async def set_speed(request: SpeedRequest):
    simulator.set_speed(request.multiplier)
    return {"status": "speed_updated", "new_multiplier": simulator.speed_multiplier}


@router.get("/handler-types")
async def list_handler_types():
    return [
        {"handler_type": handler_type, "description": description}
        for handler_type, description in HANDLER_TYPES.items()
    ]


@router.post("/sim/handler-type")
async def update_handler_type(request: HandlerTypeRequest):
    if request.handler_type not in HANDLER_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported handler type")
    return {
        "status": "handler_view_updated",
        "handler_type": request.handler_type,
        "processing": "centralized",
    }

# --- Thread REST endpoints ---

@router.get("/threads")
async def list_threads(x_handler_type: str | None = Header(default=None, alias="X-Handler-Type")):
    """Returns all thread states for initial page load."""
    user = get_current_user()
    if x_handler_type:
        require_handler_scope(x_handler_type)
        visible_handler_types = {x_handler_type}
    else:
        visible_handler_types = user.handler_types
    threads = [thread for thread in get_all_threads() if thread.handler_type in visible_handler_types]
    return [t.model_dump(mode="json") for t in threads]

@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, x_handler_type: str | None = Header(default=None, alias="X-Handler-Type")):
    state = get_thread_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_thread_access(state, x_handler_type)
    return state.model_dump(mode="json")


@router.get("/threads/{thread_id}/audit")
async def get_thread_audit(thread_id: str, x_handler_type: str | None = Header(default=None, alias="X-Handler-Type")):
    state = get_thread_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_thread_access(state, x_handler_type)
    return get_audit_events(thread_id)


@router.get("/threads/{thread_id}/messages")
async def list_thread_messages(thread_id: str, x_handler_type: str | None = Header(default=None, alias="X-Handler-Type")):
    state = get_thread_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_thread_access(state, x_handler_type)
    return [message.model_dump(mode="json") for message in get_thread_messages(thread_id)]


@router.get("/threads/{thread_id}/export")
async def export_thread_data(thread_id: str, x_handler_type: str | None = Header(default=None, alias="X-Handler-Type")):
    state = get_thread_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_thread_access(state, x_handler_type)
    return {
        "export_version": "1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "thread": state.model_dump(mode="json"),
        "messages": [message.model_dump(mode="json") for message in get_thread_messages(thread_id)],
        "audit_events": get_audit_events(thread_id),
        "drafts": [draft.model_dump(mode="json") for draft in get_thread_drafts(thread_id)],
    }


@router.get("/admin/access-log")
async def list_access_log(limit: int = 200):
    require_role("admin")
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 1000")
    return get_access_events(limit)


@router.delete("/threads/{thread_id}/data")
async def delete_thread_retained_data(thread_id: str):
    require_role("admin")
    if not delete_thread_data(thread_id):
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"status": "deleted", "thread_id": thread_id}


@router.post("/admin/retention/purge")
async def purge_retained_data(retention_days: int | None = None):
    require_role("admin")
    days = retention_days if retention_days is not None else int(os.getenv("RETENTION_DAYS", "365"))
    if days < 1 or days > 3650:
        raise HTTPException(status_code=422, detail="Retention period must be between 1 and 3650 days")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted_threads = purge_threads_older_than(cutoff)
    return {"status": "purged", "retention_days": days, "deleted_threads": deleted_threads}


@router.patch("/threads/{thread_id}/triage")
async def override_thread_triage(
    thread_id: str,
    request: TriageOverrideRequest,
    x_handler_type: str | None = Header(default=None, alias="X-Handler-Type"),
):
    require_role("handler", "supervisor", "admin")
    state = get_thread_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_thread_access(state, x_handler_type)

    reason = request.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Override reason cannot be empty")
    if request.classification is not None and request.classification not in {"Actionable", "Informational", "Irrelevant"}:
        raise HTTPException(status_code=422, detail="Unsupported classification")
    if request.priority_level is not None and request.priority_level not in {"High", "Medium", "Low"}:
        raise HTTPException(status_code=422, detail="Unsupported priority level")
    if request.priority_score is not None and not 0 <= request.priority_score <= 100:
        raise HTTPException(status_code=422, detail="Priority score must be between 0 and 100")

    changes = request.model_dump(exclude_unset=True)
    triage = state.current_triage
    if "classification" in changes:
        triage.classification = changes["classification"]
        triage.classification_source = "human"
    if "priority_score" in changes:
        triage.priority_score = changes["priority_score"]
        triage.priority_source = "human"
    if "priority_level" in changes:
        triage.priority_level = changes["priority_level"]
        triage.priority_source = "human"
    triage.override_reason = reason
    state.last_updated = datetime.now(timezone.utc)
    save_thread_state(state)
    save_audit_events(thread_id, [{
        "step": "human_override",
        "details": {
            "classification": triage.classification,
            "priority_score": triage.priority_score,
            "priority_level": triage.priority_level,
            "reason": reason,
        },
    }])
    await manager.broadcast_state(state.model_dump(mode="json"))
    return state.model_dump(mode="json")


@router.patch("/threads/{thread_id}/actions/{action_id}")
async def update_action(thread_id: str, action_id: str, request: ActionUpdateRequest, x_handler_type: str | None = Header(default=None, alias="X-Handler-Type")):
    require_role("handler", "supervisor", "admin")
    state = get_thread_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_thread_access(state, x_handler_type)

    action = next(
        (item for item in state.current_triage.required_actions if item.action_id == action_id),
        None,
    )
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    changes = request.model_dump(exclude_unset=True)
    if "task_description" in changes and not changes["task_description"].strip():
        raise HTTPException(status_code=422, detail="Action description cannot be empty")

    updated_action = action.model_copy(update=changes)
    state.current_triage.required_actions = [
        updated_action if item.action_id == action_id else item
        for item in state.current_triage.required_actions
    ]
    state.last_updated = datetime.now(timezone.utc)
    save_thread_state(state)
    await manager.broadcast_state(state.model_dump(mode="json"))
    return state.model_dump(mode="json")


@router.post("/threads/{thread_id}/notes")
async def add_thread_note(thread_id: str, request: NoteRequest, x_handler_type: str | None = Header(default=None, alias="X-Handler-Type")):
    require_role("handler", "supervisor", "admin")
    state = get_thread_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_thread_access(state, x_handler_type)

    note = request.note.strip()
    if not note:
        raise HTTPException(status_code=422, detail="Note cannot be empty")

    state.internal_notes.append(note)
    state.last_updated = datetime.now(timezone.utc)
    save_thread_state(state)
    await manager.broadcast_state(state.model_dump(mode="json"))
    return state.model_dump(mode="json")


@router.delete("/threads/{thread_id}/notes/{note_index}")
async def delete_thread_note(thread_id: str, note_index: int, x_handler_type: str | None = Header(default=None, alias="X-Handler-Type")):
    require_role("handler", "supervisor", "admin")
    state = get_thread_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_thread_access(state, x_handler_type)
    if note_index < 0 or note_index >= len(state.internal_notes):
        raise HTTPException(status_code=404, detail="Note not found")

    state.internal_notes.pop(note_index)
    state.last_updated = datetime.now(timezone.utc)
    save_thread_state(state)
    await manager.broadcast_state(state.model_dump(mode="json"))
    return state.model_dump(mode="json")


@router.get("/threads/{thread_id}/drafts")
async def list_thread_drafts(thread_id: str, x_handler_type: str | None = Header(default=None, alias="X-Handler-Type")):
    state = get_thread_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_thread_access(state, x_handler_type)
    return [draft.model_dump(mode="json") for draft in get_thread_drafts(thread_id)]


@router.post("/threads/{thread_id}/drafts")
async def create_thread_draft(thread_id: str, request: DraftRequest, x_handler_type: str | None = Header(default=None, alias="X-Handler-Type")):
    require_role("handler", "supervisor", "admin")
    state = get_thread_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_thread_access(state, x_handler_type)
    if request.draft_type not in {"external_reply", "internal_note"}:
        raise HTTPException(status_code=422, detail="Unsupported draft type")

    triage = state.current_triage
    actions = "; ".join(
        action.task_description for action in triage.required_actions if not action.is_resolved
    ) or "No unresolved actions"
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You draft insurance operations text for a human handler. "
            "Use only the supplied triage facts. Never invent cover decisions, dates, "
            "claim outcomes, commitments, or missing personal details. "
            "For an external reply, be polite and ask the handler to verify facts before sending. "
            "For an internal note, be concise and action-oriented. Return plain text only."
        )),
        ("human", (
            "Draft type: {draft_type}\nSummary: {summary}\nPriority: {priority}\n"
            "Policy: {policy}\nCustomer: {customer}\nOutstanding actions: {actions}"
        )),
    ])
    draft_chain = prompt | _qa_llm.with_structured_output(DraftResult).with_fallbacks([
        _qa_fallback_llm.with_structured_output(DraftResult),
    ])
    result = await provider_backpressure.ainvoke(lambda: draft_chain.ainvoke({
        "draft_type": request.draft_type,
        "summary": triage.one_line_summary,
        "priority": f"{triage.priority_level} ({triage.priority_score})",
        "policy": triage.entities.policy_reference or "Unknown",
        "customer": triage.entities.customer_name or "Unknown",
        "actions": actions,
    }), "draft_generation", "gpt-4o", cache_key("draft", thread_id, request.draft_type, triage.one_line_summary, actions))
    now = datetime.now(timezone.utc)
    draft = ReplyDraft(
        draft_id=str(uuid4()),
        thread_id=thread_id,
        draft_type=request.draft_type,
        body=result.body.strip(),
        created_at=now,
        updated_at=now,
    )
    save_reply_draft(draft)
    return draft.model_dump(mode="json")


@router.patch("/drafts/{draft_id}")
async def update_draft(draft_id: str, request: DraftUpdateRequest, x_handler_type: str | None = Header(default=None, alias="X-Handler-Type")):
    require_role("handler", "supervisor", "admin")
    draft = get_reply_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    state = get_thread_state(draft.thread_id)
    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")
    _require_thread_access(state, x_handler_type)
    changes = request.model_dump(exclude_unset=True)
    if "body" in changes and not changes["body"].strip():
        raise HTTPException(status_code=422, detail="Draft body cannot be empty")
    if "status" in changes and changes["status"] not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Unsupported draft status")
    updated = draft.model_copy(update={**changes, "updated_at": datetime.now(timezone.utc)})
    save_reply_draft(updated)
    return updated.model_dump(mode="json")

# --- Q&A Engine ---

_qa_llm = ChatOpenAI(model="gpt-4o", temperature=0.2)
_qa_fallback_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

@router.post("/qa")
async def ask_question(request: QARequest, x_handler_type: str | None = Header(default=None, alias="X-Handler-Type")):
    requested_handler = x_handler_type or "Claims"
    if request.thread_id:
        state = get_thread_state(request.thread_id)
        if state:
            _require_thread_access(state, requested_handler)
        threads = [state] if state else []
    else:
        threads = [thread for thread in get_all_threads() if thread.handler_type == requested_handler]

    if not threads:
        return {"answer": "No thread data available yet. Start the simulation first."}

    retrieved_messages = _retrieve_messages(threads, request.question)
    context_lines = []
    for t in threads:
        tr = t.current_triage
        actions = "; ".join(a.task_description for a in tr.required_actions) or "None"
        context_lines.append(
            f"Thread {t.thread_id} | {tr.classification} | {tr.priority_level} ({tr.priority_score}) | "
            f"Policy: {tr.entities.policy_reference or 'N/A'} | "
            f"Broker: {tr.entities.broker_name or 'N/A'} | "
            f"Customer: {tr.entities.customer_name or 'N/A'} | "
            f"Summary: {tr.one_line_summary} | Actions: {actions}"
        )

    thread_context = "\n".join(context_lines)
    message_context = "\n\n".join(
        f"Source [{message['thread_id']} / {message['message_id']}]\n"
            f"From: {redact_sender(message['sent_from'])}\nSubject: {message['subject']}\n"
            f"Sent: {message['date_sent']}\nBody:\n{sanitize_untrusted_email(redact_message_body(message['body']))[0]}"
        for message in retrieved_messages
    ) or "No matching original messages were found."

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are an AI assistant for insurance claims handlers at Aviva. "
         "Answer only from the supplied thread summaries and original email sources. "
         "Do not invent facts or infer policy cover. If the answer is not supported, say so clearly. "
         "Cite supporting messages inline using the exact format [thread_id / message_id]. "
         "Be concise and specific.\n\n"
         "Thread summaries:\n{thread_context}\n\n"
         "Retrieved original email sources:\n{message_context}"),
        ("human", "{question}")
    ])

    chain = prompt | _qa_llm.with_fallbacks([_qa_fallback_llm])
    qa_cache_key = cache_key(
        "qa",
        request.question,
        request.thread_id or "all",
        "|".join(f"{thread.thread_id}:{thread.last_updated.isoformat()}" for thread in threads),
    )
    result = await provider_backpressure.ainvoke(lambda: chain.ainvoke({
        "thread_context": thread_context,
        "message_context": message_context,
        "question": request.question,
    }), "question_answering", "gpt-4o", qa_cache_key)

    return {
        "answer": result.content,
        "sources": [
            {
                "thread_id": message["thread_id"],
                "message_id": message["message_id"],
                "subject": message["subject"],
                "sent_from": message["sent_from"],
                "date_sent": message["date_sent"],
            }
            for message in retrieved_messages
        ],
    }


@router.get("/provider-metrics")
async def get_provider_metrics():
    return provider_metrics.summary()


@router.get("/observability/status")
async def observability_status():
    require_role("supervisor", "auditor", "admin")
    return {
        "langfuse_enabled": langfuse_observability.enabled,
        "last_error": langfuse_observability.last_error,
    }


@router.get("/operations/summary")
async def operations_summary():
    require_role("supervisor", "auditor", "admin", "platform_admin")
    evaluation_path = Path(__file__).resolve().parents[3] / "artifacts" / "eval_results" / "triage_evaluation.json"
    evaluation = None
    if evaluation_path.exists():
        try:
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            evaluation = {"error": "Evaluation result file is invalid"}
    return {
        "provider_metrics": provider_metrics.summary(),
        "observability": {
            "langfuse_enabled": langfuse_observability.enabled,
            "last_error": langfuse_observability.last_error,
            "project_url": os.getenv("LANGFUSE_PROJECT_URL", "https://cloud.langfuse.com"),
        },
        "debounce": await get_debounce_settings(),
        "analytics": get_analytics_recommendations(),
        "evaluation": evaluation,
    }


@router.get("/debounce-settings")
async def get_debounce_settings():
    return {
        "enabled": is_debounce_enabled(),
        "settings": [
            {"source": source, "debounce_minutes": minutes}
            for source, minutes in DEBOUNCE_SETTINGS_MINUTES.items()
        ],
        "speed_adjusted": True,
    }


@router.patch("/debounce-settings")
async def patch_debounce_settings(request: DebounceSettingsRequest):
    require_role("supervisor", "admin")
    if request.source is not None and request.source not in DEBOUNCE_SETTINGS_MINUTES:
        raise HTTPException(status_code=422, detail="Unsupported email source")
    if request.debounce_minutes is not None and not 0 <= request.debounce_minutes <= 60:
        raise HTTPException(status_code=422, detail="Debounce must be between 0 and 60 minutes")
    if request.source is None and request.debounce_minutes is not None:
        raise HTTPException(status_code=422, detail="A source is required when changing debounce minutes")

    update_debounce_settings(request.enabled, request.source, request.debounce_minutes)
    return await get_debounce_settings()


@router.get("/debounce-analytics")
async def get_debounce_analytics():
    return {"recommendations": get_analytics_recommendations()}


@router.post("/debounce-settings/apply-analytics")
async def apply_debounce_analytics():
    require_role("supervisor", "admin")
    return {
        "status": "analytics_applied",
        "recommendations": apply_analytics_recommendations(),
        "settings": await get_debounce_settings(),
    }