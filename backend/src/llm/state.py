from typing import TypedDict, List, Optional, Dict, Any
from src.core.models import EmailMessage, ExtractedEntities, ActionItem

class ThreadTriageState(TypedDict):
    trace_id: str
    # Core Inputs
    current_message: EmailMessage
    handler_type: str
    existing_messages: List[EmailMessage]
    
    # State Updates
    classification: Optional[str]
    classification_reasoning: Optional[str]
    classification_confidence: Optional[float]
    calibrated_confidence: Optional[float]
    entities: Optional[ExtractedEntities]
    new_actions: Optional[List[ActionItem]]
    existing_actions: Optional[List[ActionItem]]
    priority_score: Optional[int]
    priority_level: Optional[str]
    urgency_justification: Optional[str]
    priority_confidence: Optional[float]
    extraction_confidence: Optional[float]
    thread_summary: Optional[str]
    audit_trail: List[Dict[str, Any]]