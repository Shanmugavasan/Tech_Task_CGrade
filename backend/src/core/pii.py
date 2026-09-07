import re


EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")
POLICY_PATTERN = re.compile(r"\b(?:PIN|HOM|MTR|LIA)[-A-Z0-9]{5,}\b", re.IGNORECASE)


def redact_for_model(value: str) -> str:
    """Remove direct contact identifiers while retaining operational context."""
    redacted = EMAIL_PATTERN.sub("[EMAIL REDACTED]", value)
    redacted = PHONE_PATTERN.sub("[PHONE REDACTED]", redacted)
    return redacted


def redact_sender(sender: str) -> str:
    return EMAIL_PATTERN.sub("[SENDER REDACTED]", sender)


def redact_message_body(value: str) -> str:
    return redact_for_model(value)
