import asyncio
import hashlib
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar
from src.core.observability import langfuse_observability


T = TypeVar("T")


@dataclass
class ProviderMetric:
    trace_id: str
    operation: str
    model: str
    elapsed_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    success: bool
    cache_hit: bool


class ProviderMetrics:
    def __init__(self):
        self._metrics: list[ProviderMetric] = []
        self._lock = threading.Lock()

    def record(self, operation: str, model: str, started_at: float, result: Any = None, error: bool = False, trace_id: str = "", cache_hit: bool = False) -> None:
        usage = getattr(result, "usage_metadata", {}) or {}
        prompt_tokens = int(usage.get("input_tokens", 0))
        completion_tokens = int(usage.get("output_tokens", 0))
        total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
        estimated_cost = (prompt_tokens * 0.00000015) + (completion_tokens * 0.0000006)
        metric = ProviderMetric(
            trace_id=trace_id,
            operation=operation,
            model=model,
            elapsed_ms=round((time.monotonic() - started_at) * 1000, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=round(estimated_cost, 8),
            success=not error,
            cache_hit=cache_hit,
        )
        with self._lock:
            self._metrics.append(metric)
        langfuse_observability.record(
            trace_id,
            operation,
            model,
            metric.elapsed_ms,
            metric.success,
            cache_hit,
            metric.prompt_tokens,
            metric.completion_tokens,
            metric.total_tokens,
            metric.estimated_cost_usd,
        )

    def summary(self) -> dict[str, Any]:
        with self._lock:
            metrics = list(self._metrics)
        return {
            "request_count": len(metrics),
            "success_count": sum(metric.success for metric in metrics),
            "failure_count": sum(not metric.success for metric in metrics),
            "total_elapsed_ms": round(sum(metric.elapsed_ms for metric in metrics), 2),
            "total_prompt_tokens": sum(metric.prompt_tokens for metric in metrics),
            "total_completion_tokens": sum(metric.completion_tokens for metric in metrics),
            "total_tokens": sum(metric.total_tokens for metric in metrics),
            "estimated_cost_usd": round(sum(metric.estimated_cost_usd for metric in metrics), 8),
            "cache_hit_count": sum(metric.cache_hit for metric in metrics),
            "by_operation": {
                operation: {
                    "request_count": sum(metric.operation == operation for metric in metrics),
                    "total_elapsed_ms": round(sum(metric.elapsed_ms for metric in metrics if metric.operation == operation), 2),
                    "total_tokens": sum(metric.total_tokens for metric in metrics if metric.operation == operation),
                }
                for operation in sorted({metric.operation for metric in metrics})
            },
        }


provider_metrics = ProviderMetrics()


class ProviderCache:
    def __init__(self, ttl_seconds: float = 30.0):
        self._ttl_seconds = ttl_seconds
        self._entries: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                return None
            created_at, value = entry
            if time.monotonic() - created_at > self._ttl_seconds:
                del self._entries[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


provider_cache = ProviderCache()


def cache_key(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


class ProviderBackpressure:
    """Small in-process guard for provider concurrency and request pacing."""

    def __init__(self, max_concurrent: int = 4, min_interval_seconds: float = 0.1):
        self._sync_slots = threading.BoundedSemaphore(max_concurrent)
        self._async_slots = asyncio.Semaphore(max_concurrent)
        self._sync_lock = threading.Lock()
        self._async_lock = asyncio.Lock()
        self._min_interval_seconds = min_interval_seconds
        self._last_request = 0.0

    def _wait_for_slot(self) -> None:
        if not self._sync_slots.acquire(timeout=30):
            raise TimeoutError("LLM provider concurrency limit reached")
        with self._sync_lock:
            wait = self._min_interval_seconds - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    def invoke(self, operation: Callable[[], T], operation_name: str = "unknown", model: str = "unknown", cache_key_value: str | None = None) -> T:
        trace_id = str(uuid.uuid4())
        if cache_key_value:
            cached = provider_cache.get(cache_key_value)
            if cached is not None:
                provider_metrics.record(operation_name, model, time.monotonic(), cached, trace_id=trace_id, cache_hit=True)
                return cached
        started_at = time.monotonic()
        self._wait_for_slot()
        try:
            result = operation()
            if cache_key_value:
                provider_cache.set(cache_key_value, result)
            provider_metrics.record(operation_name, model, started_at, result, trace_id=trace_id)
            return result
        except Exception:
            provider_metrics.record(operation_name, model, started_at, error=True, trace_id=trace_id)
            raise
        finally:
            self._sync_slots.release()

    async def ainvoke(self, operation: Callable[[], Awaitable[T]], operation_name: str = "unknown", model: str = "unknown", cache_key_value: str | None = None) -> T:
        trace_id = str(uuid.uuid4())
        if cache_key_value:
            cached = provider_cache.get(cache_key_value)
            if cached is not None:
                provider_metrics.record(operation_name, model, time.monotonic(), cached, trace_id=trace_id, cache_hit=True)
                return cached
        started_at = time.monotonic()
        async with self._async_slots:
            async with self._async_lock:
                wait = self._min_interval_seconds - (time.monotonic() - self._last_request)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_request = time.monotonic()
            try:
                result = await operation()
                if cache_key_value:
                    provider_cache.set(cache_key_value, result)
                provider_metrics.record(operation_name, model, started_at, result, trace_id=trace_id)
                return result
            except Exception:
                provider_metrics.record(operation_name, model, started_at, error=True, trace_id=trace_id)
                raise


provider_backpressure = ProviderBackpressure()
