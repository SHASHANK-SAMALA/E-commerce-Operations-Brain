"""Investigation status store — Redis-backed with in-memory fallback.

Redis enables multi-worker Uvicorn deployments to share investigation state.
Falls back to in-memory dict if Redis is unavailable (dev without Docker).
"""

from __future__ import annotations

import json

import structlog

from ecommerce_brain.exceptions import StatusStoreError

log = structlog.get_logger(__name__)

_TTL_RUNNING_SECONDS = 3600 * 6   # 6 hours — hard cap for stuck investigations
_TTL_TERMINAL_SECONDS = 86400     # 24 hours — completed / error / blocked results
_TERMINAL_STATUSES = frozenset({"completed", "error", "blocked", "interrupted"})


class StatusStore:
    """Redis-backed investigation status store with in-memory fallback.

    Designed for dependency injection in tests — pass a custom instance
    instead of relying on the module-level singleton.
    """

    def __init__(self) -> None:
        self._redis_client = None
        self._use_redis: bool = False
        self._fallback_store: dict[str, dict] = {}

    def _get_redis(self):
        """Return a live Redis client, or None if Redis is unavailable."""
        if self._redis_client is not None:
            return self._redis_client
        try:
            import redis

            from ecommerce_brain.config.settings import get_settings
            settings = get_settings()
            client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            self._redis_client = client
            self._use_redis = True
            log.info("status_store.redis_connected", url=settings.redis_url)
            return self._redis_client
        except StatusStoreError:
            raise
        except Exception as exc:
            log.warning("status_store.redis_unavailable", error=str(exc)[:100])
            self._use_redis = False
            return None

    @staticmethod
    def _key(query_id: str) -> str:
        """Return the Redis key for a given query_id."""
        return f"investigation:{query_id}"

    def get_status(self, query_id: str) -> dict | None:
        """Return the status dict for *query_id*, or None if not found.

        Args:
            query_id: Investigation identifier.

        Returns:
            Status dict or None if no record exists.
        """
        r = self._get_redis()
        if r and self._use_redis:
            raw = r.get(self._key(query_id))
            return json.loads(raw) if raw else None
        return self._fallback_store.get(query_id)

    def set_status(self, query_id: str, data: dict) -> None:
        """Overwrite the full status record for *query_id*.

        Args:
            query_id: Investigation identifier.
            data: Complete status dict to persist.
        """
        r = self._get_redis()
        if r and self._use_redis:
            status = data.get("status", "")
            ttl = _TTL_TERMINAL_SECONDS if status in _TERMINAL_STATUSES else _TTL_RUNNING_SECONDS
            r.set(self._key(query_id), json.dumps(data, default=str), ex=ttl)
        else:
            self._fallback_store[query_id] = data

    def update_status(self, query_id: str, updates: dict) -> None:
        """Merge *updates* into the existing status record.

        Args:
            query_id: Investigation identifier.
            updates: Partial dict to merge into the existing record.
        """
        current = self.get_status(query_id)
        if current is None:
            current = {}
        current.update(updates)
        self.set_status(query_id, current)

    def reconcile_running_investigations(self) -> int:
        """Mark any 'running' investigations as 'interrupted' on server startup.

        Background tasks die when the API process exits, but Redis still holds
        the 'running' status. Without reconciliation the frontend polls forever.

        Returns:
            Number of investigations transitioned to 'interrupted'.
        """
        r = self._get_redis()
        if not (r and self._use_redis):
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


# Module-level singleton — callers import the functions below, not the class directly.
_store = StatusStore()


def get_status(query_id: str) -> dict | None:
    """Return the status dict for *query_id*, or None if not found."""
    return _store.get_status(query_id)


def set_status(query_id: str, data: dict) -> None:
    """Overwrite the full status record for *query_id*."""
    _store.set_status(query_id, data)


def update_status(query_id: str, updates: dict) -> None:
    """Merge *updates* into the existing status record."""
    _store.update_status(query_id, updates)


def reconcile_running_investigations() -> int:
    """Mark stale 'running' investigations as 'interrupted' on startup."""
    return _store.reconcile_running_investigations()
