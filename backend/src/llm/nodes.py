from pydantic import BaseModel, Field
from typing import List, Dict, Any
from difflib import SequenceMatcher
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.llm.state import ThreadTriageState
from src.core.models import ExtractedEntities, ActionItem
from src.core.provider import provider_backpressure
from src.core.pii import redact_message_body, redact_sender
from src.core.prompt_safety import sanitize_untrusted_email

MODEL_NAME = "gpt-4o-mini"
PROMPT_VERSION = "triage-v1"


def safe_message_body(value: str) -> str:
    return sanitize_untrusted_email(redact_message_body(value))[0]


def audit_event(state: ThreadTriageState, step: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": step,
        "message_id": state["current_message"].message_id,
        "model": MODEL_NAME,
        "prompt_version": PROMPT_VERSION,
        "trace_id": state.get("trace_id"),
        "details": details,
    }


def apply_importance_adjustment(priority_score: int, importance_flag: str | None) -> tuple[int, str]:
    """Applies the explicit source importance guard after LLM scoring."""
    score = priority_score
    if (importance_flag or "").lower() == "high" and score < 40:
        score = 40

    if score >= 80:
        level = "High"
    elif score >= 40:
        level = "Medium"
    else:
        level = "Low"
    return score, level


def apply_policy_guardrails(
    classification: str,
    priority_score: int,
    priority_level: str,
    importance_flag: str | None,
    body: str,
    actions: list[ActionItem],
) -> tuple[int, str, list[ActionItem], list[str]]:
    """Apply deterministic safety floors after model interpretation."""
    evidence = body.lower()
    reasons: list[str] = []
    score = priority_score
    normalized_level = priority_level

    if classification == "Irrelevant":
        if actions:
            reasons.append("Irrelevant classification cleared model actions")
        return 0, "Low", [], reasons

    if (importance_flag or "").lower() == "high" and score < 40:
        score = 40
        reasons.append("High importance floor applied")

    urgent_terms = (
        "legal notice", "letter before action", "solicitor", "uninhabitable",
        "actively uninhabitable", "unsafe", "burglary", "stolen", "theft",
    )
    if any(term in evidence for term in urgent_terms) and score < 80:
        score = 80
        reasons.append("Urgent legal, safety, or theft floor applied")

    if score >= 80:
        normalized_level = "High"
    elif score >= 40:
        normalized_level = "Medium"
    else:
        normalized_level = "Low"
    return score, normalized_level, actions, reasons


def calibrate_confidence(
    classification_confidence: float,
    extraction_confidence: float,
    priority_confidence: float,
    classification: str,
    actions: list[ActionItem],
    entities: ExtractedEntities | None,
    guardrail_reasons: list[str],
) -> float:
    """Convert model confidence into an evidence-aware review signal."""
    values = [classification_confidence]
    if classification == "Actionable":
        values.extend([extraction_confidence, priority_confidence])
        if not actions:
            values.append(0.5)
        if not entities or not (entities.policy_reference or entities.customer_name or entities.third_parties):
            values.append(0.6)
    calibrated = sum(values) / len(values) if values else 0.0
    if guardrail_reasons:
        calibrated -= min(0.2, 0.05 * len(guardrail_reasons))
    return round(max(0.0, min(1.0, calibrated)), 3)


def consolidate_actions(existing_actions: list[ActionItem], new_actions: list[ActionItem]) -> list[ActionItem]:
    """Merge repeated task wording while retaining handler resolution state."""
    consolidated: list[ActionItem] = []
    normalized_indexes: dict[str, int] = {}

    for action in [*existing_actions, *new_actions]:
        normalized = " ".join(action.task_description.lower().split())
        matching_index = normalized_indexes.get(normalized)
        if matching_index is None:
            for candidate, candidate_index in normalized_indexes.items():
                if SequenceMatcher(None, normalized, candidate).ratio() >= 0.82:
                    matching_index = candidate_index
                    break

        if matching_index is not None:
            current = consolidated[matching_index]
            current.deadline = action.deadline or current.deadline
            current.is_resolved = action.is_resolved or current.is_resolved
            continue

        action.action_id = action.action_id or f"action-{len(consolidated) + 1}"
        normalized_indexes[normalized] = len(consolidated)
        consolidated.append(action)

    return consolidated

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
fallback_llm = ChatOpenAI(model="gpt-4o", temperature=0.0)

class ClassificationResult(BaseModel):
    classification: str = Field(..., description="'Actionable', 'Informational', or 'Irrelevant'")
    reasoning: str = Field(..., description="Brief rationale for the classification decision")
    confidence: float = Field(..., ge=0.0, le=1.0)

class ExtractionResult(BaseModel):
    entities: ExtractedEntities
    actions: List[ActionItem]
    confidence: float = Field(..., ge=0.0, le=1.0)

class ScoringResult(BaseModel):
    priority_score: int = Field(..., ge=0, le=100, description="Priority rating from 0 to 100")
    priority_level: str = Field(..., description="'High', 'Medium', or 'Low'")
    urgency_justification: str
    confidence: float = Field(..., ge=0.0, le=1.0)

class SummaryResult(BaseModel):
    consolidated_summary: str = Field(..., description="A clear, updated single-sentence thread summary")

def context_merger_node(state: ThreadTriageState) -> Dict[str, Any]:
    audit_entry = audit_event(state, "context_merger", {
        "is_followup": len(state.get("existing_messages", [])) > 0,
        "message_count": len(state.get("existing_messages", [])) + 1,
    })
    return {"audit_trail": state.get("audit_trail", []) + [audit_entry]}

def classification_node(state: ThreadTriageState) -> Dict[str, Any]:
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an insurance triage engine for a {handler_type} handler. "
            "Classify the incoming message into exactly one of:\n"
            "- 'Actionable': Requires handler action, verification, review, or customer contact.\n"
            "- 'Informational': Courtesy updates, positive feedback, or system acknowledgements to archive.\n"
            "- 'Irrelevant': Spam, marketing, or messages intended for an unrelated team."
        )),
        ("human", "Subject: {subject}\nSender: {sender}\nBody:\n{body}")
    ])
    classifier_model = llm.with_structured_output(ClassificationResult).with_fallbacks([
        fallback_llm.with_structured_output(ClassificationResult),
    ])
    classifier_chain = prompt | classifier_model
    result = provider_backpressure.invoke(lambda: classifier_chain.invoke({
        "handler_type": state["handler_type"],
        "subject": state["current_message"].subject,
        "sender": redact_sender(str(state["current_message"].sent_from)),
        "body": safe_message_body(state["current_message"].body)
    }), "classifier", MODEL_NAME)
    return {
        "classification": result.classification,
        "classification_reasoning": result.reasoning,
        "classification_confidence": result.confidence,
        "audit_trail": state.get("audit_trail", []) + [audit_event(
            state,
            "classifier",
            {"classification": result.classification, "reasoning": result.reasoning, "confidence": result.confidence},
        )],
    }

def task_extraction_node(state: ThreadTriageState) -> Dict[str, Any]:
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Extract insurance policy references, involved brokers/customers/third parties, "
            "and all concrete, actionable tasks requested in this communication."
        )),
        ("human", "Subject: {subject}\nSender: {sender}\nBody:\n{body}")
    ])
    extraction_model = llm.with_structured_output(ExtractionResult).with_fallbacks([
        fallback_llm.with_structured_output(ExtractionResult),
    ])
    extraction_chain = prompt | extraction_model
    result = provider_backpressure.invoke(lambda: extraction_chain.invoke({
        "subject": state["current_message"].subject,
        "sender": redact_sender(str(state["current_message"].sent_from)),
        "body": safe_message_body(state["current_message"].body)
    }), "task_extraction", MODEL_NAME)
    return {
        "entities": result.entities,
        "new_actions": result.actions,
        "extraction_confidence": result.confidence,
        "audit_trail": state.get("audit_trail", []) + [audit_event(
            state,
            "task_extraction",
            {"action_count": len(result.actions), "confidence": result.confidence},
        )],
    }

def priority_scoring_node(state: ThreadTriageState) -> Dict[str, Any]:
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Evaluate operational urgency and business impact for an insurance claim.\n"
            "- Score 80-100 (High): Property actively uninhabitable, impending SLA breach, legal/police notices, burglary with unsecured premises.\n"
            "- Score 40-79 (Medium): Standard claims documentation, adjuster scheduling, supplier quotes.\n"
            "- Score 0-39 (Low): Routine confirmations, non-urgent inquiries.\n"
            "Treat an explicit high email importance flag as an escalation signal, "
            "but do not let it override the actual business impact without explanation."
        )),
        ("human", "Importance flag: {importance_flag}\nTasks:\n{tasks}\nEmail Body:\n{body}")
    ])
    tasks_text = "\n".join([f"- {t.task_description}" for t in state.get("new_actions", [])])
    scorer_model = llm.with_structured_output(ScoringResult).with_fallbacks([
        fallback_llm.with_structured_output(ScoringResult),
    ])
    scorer_chain = prompt | scorer_model
    result = provider_backpressure.invoke(lambda: scorer_chain.invoke({
        "tasks": tasks_text,
        "importance_flag": state["current_message"].importance_flag or "not set",
        "body": safe_message_body(state["current_message"].body)
    }), "priority_scoring", MODEL_NAME)
    importance_flag = (state["current_message"].importance_flag or "").lower()
    priority_score, priority_level = apply_importance_adjustment(
        result.priority_score,
        importance_flag,
    )

    justification = result.urgency_justification
    if importance_flag == "high":
        justification = f"{justification} Source email is explicitly marked high importance."
    return {
        "priority_score": priority_score,
        "priority_level": priority_level,
        "urgency_justification": justification,
        "priority_confidence": result.confidence,
        "audit_trail": state.get("audit_trail", []) + [audit_event(
            state,
            "priority_scoring",
            {
                "priority_score": priority_score,
                "priority_level": priority_level,
                "urgency_justification": justification,
                "importance_flag": importance_flag or None,
                "confidence": result.confidence,
            },
        )],
    }

def consolidation_node(state: ThreadTriageState) -> Dict[str, Any]:
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Generate a concise, factual, single-line summary representing the current state "
            "of this insurance thread. Highlight outstanding actions."
        )),
        ("human", "Previous Summary: {prev_summary}\n"
                  "Earlier Thread Messages:\n{history}\n"
                  "Latest Message Body:\n{body}")
    ])
    history = "\n\n".join(
        f"Subject: {message.subject}\nFrom: {redact_sender(str(message.sent_from))}\nBody: {safe_message_body(message.body)}"
        for message in state.get("existing_messages", [])
    ) or "No earlier messages."
    summary_model = llm.with_structured_output(SummaryResult).with_fallbacks([
        fallback_llm.with_structured_output(SummaryResult),
    ])
    summary_chain = prompt | summary_model
    result = provider_backpressure.invoke(lambda: summary_chain.invoke({
        "prev_summary": state.get("thread_summary") or "New thread initiated.",
        "history": history,
        "body": safe_message_body(state["current_message"].body)
    }), "consolidation", MODEL_NAME)
    
    all_actions = consolidate_actions(
        list(state.get("existing_actions") or []),
        list(state.get("new_actions") or []),
    )
    priority_score, priority_level, all_actions, guardrail_reasons = apply_policy_guardrails(
        state.get("classification") or "Irrelevant",
        state.get("priority_score") or 0,
        state.get("priority_level") or "Low",
        state["current_message"].importance_flag,
        state["current_message"].body,
        all_actions,
    )
    calibrated_confidence = calibrate_confidence(
        state.get("classification_confidence") or 0.0,
        state.get("extraction_confidence") or 0.0,
        state.get("priority_confidence") or 0.0,
        state.get("classification") or "Irrelevant",
        all_actions,
        state.get("entities"),
        guardrail_reasons,
    )
    audit_trail = state.get("audit_trail", [])
    if guardrail_reasons:
        audit_trail = audit_trail + [audit_event(
            state,
            "policy_guardrails",
            {"reasons": guardrail_reasons, "priority_score": priority_score, "priority_level": priority_level},
        )]
    return {
        "thread_summary": result.consolidated_summary,
        "existing_actions": all_actions,
        "priority_score": priority_score,
        "priority_level": priority_level,
        "calibrated_confidence": calibrated_confidence,
        "audit_trail": audit_trail + [audit_event(
            state,
            "consolidation",
            {"action_count": len(all_actions)},
        )],
    }