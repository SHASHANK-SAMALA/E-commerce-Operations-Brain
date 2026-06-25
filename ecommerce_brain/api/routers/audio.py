"""Audio input router — Whisper transcription via Azure OpenAI."""

from __future__ import annotations

import io
from functools import lru_cache

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from openai import AzureOpenAI

from ecommerce_brain.api.deps import require_api_key
from ecommerce_brain.config.settings import get_settings

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/audio", tags=["audio"])

_WHISPER_SIZE_LIMIT = 25 * 1024 * 1024  # 25 MB — Azure Whisper hard cap
_UNAVAILABLE_MARKERS = frozenset({"Route is not found", "404", "502", "deployment", "not found"})


@lru_cache(maxsize=1)
def _whisper_client() -> AzureOpenAI:
    """Module-level singleton — one client per worker process."""
    s = get_settings()
    return AzureOpenAI(
        azure_endpoint=s.azure_openai_endpoint,
        api_key=s.azure_openai_api_key,
        api_version=s.azure_openai_api_version,
    )


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    _: str = Depends(require_api_key),
):
    """Transcribe audio to text using Azure Whisper. Returns transcription for investigation."""
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    if file.size and file.size > _WHISPER_SIZE_LIMIT:
        raise HTTPException(status_code=400, detail="Audio file exceeds 25MB limit")

    audio_bytes = await file.read()
    audio_buf = io.BytesIO(audio_bytes)
    audio_buf.name = file.filename or "audio.webm"

    try:
        transcription = _whisper_client().audio.transcriptions.create(
            model=get_settings().azure_openai_whisper_deployment,
            file=audio_buf,
        )
        return {"text": transcription.text}
    except Exception as exc:
        err = str(exc)
        log.error("audio.transcribe.failed", error=err[:200])
        if any(marker in err for marker in _UNAVAILABLE_MARKERS):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Voice transcription is unavailable on this deployment. "
                    "Please type your query instead."
                ),
            ) from exc
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc!s}") from exc
