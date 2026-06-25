"""Investigation status store — Redis-backed with in-memory fallback.

Redis enables multi-worker Uvicorn deployments to share investigation state.
Falls back to in-memory dict if Redis is unavailable (dev without Docker).
"""

from __future__ import annotations

import json

import structlog

log = structlog.get_logger(__name__)

_TTL_RUNNING_SECONDS = 3600 * 6  # 6 hours — hard cap for stuck investigations
_TTL_TERMINAL_SECONDS = 86400    # 24 hours — completed / error / blocked results

_redis_client = None
_fallback_store: dict[str, dict] = {}
_use_redis = False


def _get_redis():
    global _redis_client, _use_redis
    if _redis_client is not None:
        return _redis_client
    try:
        import redis

        from ecommerce_brain.config.settings import get_settings
        settings = get_settings()
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        _redis_client.ping()
        _use_redis = True
        log.info("status_store.redis_connected", url=settings.redis_url)
        return _redis_client
    except Exception as exc:
        log.warning("status_store.redis_unavailable", error=str(exc)[:100])
        _use_redis = False
        return None


def _key(query_id: str) -> str:
    return f"investigation:{query_id}"


def get_status(query_id: str) -> dict | None:
    r = _get_redis()
    if r and _use_redis:
        raw = r.get(_key(query_id))
        return json.loads(raw) if raw else None
    return _fallback_store.get(query_id)


_TERMINAL_STATUSES = frozenset({"completed", "error", "blocked", "interrupted"})


def set_status(query_id: str, data: dict) -> None:
    r = _get_redis()
    if r and _use_redis:
        status = data.get("status", "")
        ttl = _TTL_TERMINAL_SECONDS if status in _TERMINAL_STATUSES else _TTL_RUNNING_SECONDS
        r.set(_key(query_id), json.dumps(data, default=str), ex=ttl)
    else:
        _fallback_store[query_id] = data


def update_status(query_id: str, updates: dict) -> None:
    current = get_status(query_id)
    if current is None:
        current = {}
    current.update(updates)
    set_status(query_id, current)


def reconcile_running_investigations() -> int:
    """Mark any 'running' investigations as 'interrupted' on server startup.

    Background tasks die when the API process exits, but Redis still holds the
    'running' status. Without reconciliation, the frontend would poll forever.
    Returns the number of investigations reconciled.
    """
    r = _get_redis()
    if not (r and _use_redis):
        # In-memory store is process-local, so it's already empty on restart.
        return 0
    reconciled = 0
    try:
        for key in r.scan_iter(match="investigation:*"):
            raw = r.get(key)
            if not raw:
                continue
            data = json.loads(raw)
            if data.get("status") == "running":
                data["status"] = "interrupted"
                data["error"] = "Server restarted while investigation was running"
                r.set(key, json.dumps(data, default=str), ex=_TTL_TERMINAL_SECONDS)
                reconciled += 1
    except Exception as exc:
        log.warning("status_store.reconcile_failed", error=str(exc)[:200])
    if reconciled:
        log.info("status_store.reconciled", count=reconciled)
    return reconciled
