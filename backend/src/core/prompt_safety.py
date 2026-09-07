import re


INSTRUCTION_PATTERN = re.compile(
    r"(?i)\b(ignore|disregard|override)\s+(all\s+)?previous\s+instructions\b|"
    r"\b(system\s+message|developer\s+message|prompt injection|you are now)\b"
)


def sanitize_untrusted_email(value: str) -> tuple[str, bool]:
    """Mark instruction-like email text as untrusted data before prompting."""
    detected = bool(INSTRUCTION_PATTERN.search(value))
    sanitized = INSTRUCTION_PATTERN.sub("[UNTRUSTED INSTRUCTION REMOVED]", value)
    return sanitized, detected
