import os
from typing import Any


class LangfuseObservability:
    """Optional Langfuse adapter that never sends raw prompt or email content."""

    def __init__(self):
        self._client = None
        self.last_error: str | None = None
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        if public_key and secret_key:
            try:
                from langfuse import Langfuse
                self._client = Langfuse(
                    public_key=public_key,
                    secret_key=secret_key,
                    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                )
            except Exception:
                self._client = None
                self.last_error = "Langfuse client initialization failed"

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def record(
        self,
        trace_id: str,
        operation: str,
        model: str,
        elapsed_ms: float,
        success: bool,
        cache_hit: bool,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        if not self._client:
            return
        try:
            generation = self._client.start_observation(
                name="aviva-email-triage",
                as_type="generation",
                model=model,
                input={"redacted": True},
                metadata={
                    "operation": operation,
                    "trace_id": trace_id,
                    "elapsed_ms": elapsed_ms,
                    "success": success,
                    "cache_hit": cache_hit,
                },
                usage_details={
                    "input": prompt_tokens,
                    "output": completion_tokens,
                    "total": total_tokens,
                },
                cost_details={"total": estimated_cost_usd},
            )
            generation.end()
            self._client.flush()
            self.last_error = None
        except Exception as error:
            self.last_error = type(error).__name__
            # Observability must not take down triage when the telemetry service is unavailable.
            return


langfuse_observability = LangfuseObservability()
