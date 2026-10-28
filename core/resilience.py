"""Resilient retry wrapper with exponential backoff, jitter, and cooperative cancellation for Gemini API calls."""

from __future__ import annotations

import functools
import logging
import random
import time
from typing import Any, Callable, Optional, TypeVar

from google.genai import errors as genai_errors


logger = logging.getLogger("OmniResearch.Resilience")

T = TypeVar("T")

RATE_LIMIT_USER_MESSAGE = (
    "API Rate Limit Exceeded (429): Google has temporarily rate-limited your API key. "
    "If you are on the Free Tier, wait 60 seconds before retrying, decrease the number of active perspectives, "
    "or enable Pay-As-You-Go in Google AI Studio to increase your RPM quota."
)


class TaskCancelledError(Exception):
    """Raised when a background task is cooperatively aborted by the user."""


import httpx
try:
    import httpcore
    HTTPCORE_TIMEOUTS = (httpcore.ReadTimeout, httpcore.ConnectTimeout, getattr(httpcore, "RemoteProtocolError", Exception))
except ImportError:
    HTTPCORE_TIMEOUTS = ()

RETRYABLE_NETWORK_ERRORS = (
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
    httpx.NetworkError,
    TimeoutError,
    ConnectionResetError,
    ConnectionError,
    *HTTPCORE_TIMEOUTS,
)


def is_rate_limit_error(exc: BaseException) -> bool:
    """Detect whether an exception corresponds to HTTP 429 or RESOURCE_EXHAUSTED."""
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        status = str(getattr(exc, "status", "") or "").upper()
        message = str(getattr(exc, "message", "") or "").upper()
        if code == 429 or "429" in status or "RESOURCE_EXHAUSTED" in status or "RESOURCE_EXHAUSTED" in message:
            return True

    text = str(exc).upper()
    return "429" in text or "RESOURCE_EXHAUSTED" in text or "RATE LIMIT" in text or "QUOTA" in text


def is_retryable_network_error(exc: BaseException) -> bool:
    """Detect whether an exception corresponds to an HTTPX/HTTPCORE read or connect timeout."""
    if isinstance(exc, RETRYABLE_NETWORK_ERRORS):
        return True
    text = str(exc).lower()
    return any(
        term in text
        for term in (
            "readtimeout",
            "connecttimeout",
            "read timeout",
            "connect timeout",
            "timed out",
            "connection reset",
            "remoteprotocolerror",
            "remote protocol error",
        )
    )


def is_transient_server_error(exc: BaseException) -> bool:
    """Detect whether an exception corresponds to transient HTTP 5xx errors (504 DEADLINE_EXCEEDED, 503 UNAVAILABLE, etc.)."""
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        status = str(getattr(exc, "status", "") or "").upper()
        message = str(getattr(exc, "message", "") or "").upper()
        if code in {500, 502, 503, 504}:
            return True
        if any(term in status or term in message for term in ("DEADLINE_EXCEEDED", "UNAVAILABLE", "GATEWAY_TIMEOUT", "INTERNAL")):
            return True

    text = str(exc).upper()
    return any(
        term in text
        for term in (
            "504",
            "503",
            "502",
            "500",
            "DEADLINE_EXCEEDED",
            "DEADLINE EXCEEDED",
            "UNAVAILABLE",
            "GATEWAY TIMEOUT",
            "BAD GATEWAY",
        )
    )


def is_retryable_error(exc: BaseException) -> bool:
    """Return True if exc is a rate-limit, network timeout, or transient 5xx server error."""
    return is_rate_limit_error(exc) or is_retryable_network_error(exc) or is_transient_server_error(exc)


def sleep_with_cancel_check(
    duration: float,
    cancel_check: Optional[Callable[[], bool]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """Sleep for `duration` seconds in responsive slices if using standard `time.sleep`, checking `cancel_check`."""
    if cancel_check and cancel_check():
        raise TaskCancelledError("Task aborted by user.")

    if sleep_fn is not time.sleep:
        sleep_fn(duration)
        if cancel_check and cancel_check():
            raise TaskCancelledError("Task aborted by user.")
        return

    remaining = max(0.0, duration)
    step = 0.1
    while remaining > 0:
        if cancel_check and cancel_check():
            raise TaskCancelledError("Task aborted by user.")
        chunk = min(step, remaining)
        time.sleep(chunk)
        remaining -= chunk


def call_with_exponential_backoff(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = 4,
    initial_wait: float = 2.0,
    multiplier: float = 2.0,
    max_backoff: float = 30.0,
    progress_callback: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> T:
    """Execute `func(*args, **kwargs)` with exponential backoff, jitter, and cooperative cancellation checks."""
    attempt = 0
    while True:
        if cancel_check and cancel_check():
            raise TaskCancelledError("Task aborted by user.")

        try:
            result = func(*args, **kwargs)
            if cancel_check and cancel_check():
                raise TaskCancelledError("Task aborted by user.")
            return result
        except TaskCancelledError:
            raise
        except Exception as exc:
            if cancel_check and cancel_check():
                raise TaskCancelledError("Task aborted by user.")

            is_rate_limit = is_rate_limit_error(exc)
            is_net_timeout = is_retryable_network_error(exc)
            is_transient = is_transient_server_error(exc)

            if (not is_rate_limit and not is_net_timeout and not is_transient) or attempt >= max_retries:
                raise

            attempt += 1
            base_delay = min(max_backoff, initial_wait * (multiplier ** (attempt - 1)))
            jitter = random.uniform(0.0, min(1.0, base_delay * 0.25))
            wait_seconds = min(max_backoff, base_delay + jitter)

            if is_rate_limit:
                warn_msg = (
                    f"Rate limit (429 RESOURCE_EXHAUSTED) encountered. "
                    f"Retry attempt {attempt}/{max_retries} in {wait_seconds:.1f}s..."
                )
            elif is_transient:
                warn_msg = (
                    f"Transient gateway/server deadline error ({type(exc).__name__}: {str(exc)[:90]}). "
                    f"Retry attempt {attempt}/{max_retries} with exponential backoff in {wait_seconds:.1f}s..."
                )
            else:
                warn_msg = (
                    f"Gemini API / HTTP ReadTimeout encountered ({type(exc).__name__}). "
                    f"Retry attempt {attempt}/{max_retries} with extended 180s headroom in {wait_seconds:.1f}s..."
                )
            logger.warning(warn_msg)
            print(f"[WARNING] {warn_msg}", flush=True)
            if progress_callback is not None:
                progress_callback(warn_msg)

            sleep_with_cancel_check(wait_seconds, cancel_check=cancel_check, sleep_fn=sleep_fn)


def with_exponential_backoff(
    max_retries: int = 4,
    initial_wait: float = 2.0,
    multiplier: float = 2.0,
    max_backoff: float = 30.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator wrapping a callable with 429 / RESOURCE_EXHAUSTED exponential backoff."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            progress_cb = kwargs.pop("_progress_callback", None)
            cancel_cb = kwargs.pop("_cancel_check", None)
            return call_with_exponential_backoff(
                func,
                *args,
                max_retries=max_retries,
                initial_wait=initial_wait,
                multiplier=multiplier,
                max_backoff=max_backoff,
                progress_callback=progress_cb,
                cancel_check=cancel_cb,
                **kwargs,
            )

        return wrapper

    return decorator
