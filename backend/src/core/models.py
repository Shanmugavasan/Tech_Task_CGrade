from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr

# --- INGESTION MODELS ---

class Attachment(BaseModel):
    filename: str
    filesize: int
    filetype: str

class EmailMessage(BaseModel):
    """Raw email message from the ingestion source."""
    model_config = ConfigDict(from_attributes=True)
    
    message_id: str
    thread_id: str
    subject: str
    body: str
    sent_from: EmailStr
    sent_to: List[EmailStr]
    sent_cc: Optional[List[EmailStr]] = []
    date_sent: datetime
    attachments: Optional[List[Attachment]] = []
    importance_flag: Optional[str] = None

# --- LLM OUTPUT MODELS ---

class ExtractedEntities(BaseModel):
    policy_reference: Optional[str] = Field(default=None, description="Insurance policy number (e.g., PIN-HOM-123456)")
    broker_name: Optional[str] = Field(default=None, description="Name of the broker, if applicable")
    customer_name: Optional[str] = Field(default=None, description="Name of the policyholder/customer")
    third_parties: List[str] = Field(default_factory=list, description="Other involved parties (e.g., adjusters, police)")

class ActionItem(BaseModel):
    action_id: str = Field(default="")
    task_description: str = Field(..., description="Clear, actionable description of the task")
    deadline: Optional[datetime] = Field(default=None, description="Explicit or inferred deadline based on email text")
    is_resolved: bool = Field(default=False)

class LLMTriageOutput(BaseModel):
    classification: str = Field(..., description="Must be one of: 'Actionable', 'Informational', 'Irrelevant'")
    classification_reasoning: str = Field(default="", description="Reason for the classification decision")
    classification_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    calibrated_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    priority_score: int = Field(..., description="Score from 0 to 100 assessing business impact and urgency")
    priority_level: str = Field(..., description="Must be one of: 'High', 'Medium', 'Low'")
    urgency_justification: str = Field(default="", description="Reason for the urgency and priority decision")
    priority_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    entities: ExtractedEntities
    required_actions: List[ActionItem]
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    classification_source: Literal["ai", "human"] = "ai"
    priority_source: Literal["ai", "human"] = "ai"
    override_reason: str = ""
    one_line_summary: str = Field(..., description="Concise, single-sentence summary of the thread state")

# --- STATE MODELS ---

class ThreadState(BaseModel):
    thread_id: str
    handler_type: str = Field(default="Unknown")
    last_updated: datetime
    message_count: int
    current_triage: LLMTriageOutput
    internal_notes: List[str] = Field(default_factory=list)  # ← add this


class ReplyDraft(BaseModel):
    draft_id: str
    thread_id: str
    draft_type: Literal["external_reply", "internal_note"]
    body: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: datetime
    updated_at: datetime