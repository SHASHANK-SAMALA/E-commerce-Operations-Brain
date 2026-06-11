"""Audio input router — Whisper transcription via Azure OpenAI."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ecommerce_brain.api.deps import require_api_key
from ecommerce_brain.config.settings import settings

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/audio", tags=["audio"])


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    _: str = Depends(require_api_key),
):
    """Transcribe audio to text using Azure Whisper. Returns transcription for investigation."""
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    if file.size and file.size > 25 * 1024 * 1024:  # 25MB Whisper limit
        raise HTTPException(status_code=400, detail="Audio file exceeds 25MB limit")

    audio_bytes = await file.read()

    try:
        from openai import AzureOpenAI
        client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        import io
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = file.filename or "audio.webm"

        transcription = client.audio.transcriptions.create(
            model=settings.azure_openai_whisper_deployment,
            file=audio_file,
        )
        return {"text": transcription.text}
    except Exception as exc:
        err = str(exc)
        log.error("audio.transcribe.failed", error=err[:200])
        if any(k in err for k in ("Route is not found", "404", "502", "deployment", "not found")):
            raise HTTPException(
                status_code=503,
                detail="Voice transcription is unavailable on this deployment. Please type your query instead.",
            ) from exc
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc!s}") from exc
