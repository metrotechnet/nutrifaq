"""
Translation Routes - Translation and audio transcription endpoints
"""
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse, JSONResponse
import json
import uuid

from api.models import TranslateRequest
from api.logging import save_question_response
from api.translate import (
    translate_text_stream, 
    transcribe_audio_whisper, 
    translate_audio_whisper, 
    get_supported_languages
)

router = APIRouter()


@router.get("/api/languages")
def get_languages():
    """Return the list of supported translation languages."""
    return get_supported_languages()


@router.post("/api/translate")
async def translate_text_endpoint(request: TranslateRequest):
    """Translate text to target language using GPT with streaming."""
    question_id = str(uuid.uuid4())
    
    def generate():
        # Send question_id in first chunk
        yield f"data: {json.dumps({'question_id': question_id, 'chunk': ''})}\n\n"
        
        translated = ""
        for chunk in translate_text_stream(
            text=request.text,
            target_language=request.target_language,
            source_language=request.source_language
        ):
            translated += chunk
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        
        # Save translation to log
        save_question_response(
            question_id, 
            f"[TRANSLATION {request.source_language}→{request.target_language}] {request.text}",
            translated
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@router.post("/api/transcribe_audio")
async def transcribe_audio_endpoint(
    audio: UploadFile = File(...),
    language: str = Form(None)
):
    """
    Transcribe audio using Whisper (speech recognition only).
    Returns just the transcribed text without translation.
    
    Args:
        audio: Audio file to transcribe
        language: Optional ISO-639-1 language code (e.g., 'en', 'fr') for better accuracy
    """
    audio_bytes = await audio.read()
    transcribed_text = transcribe_audio_whisper(
        audio_bytes, 
        filename=audio.filename or "audio.webm",
        language=language
    )
    
    if not transcribed_text:
        return JSONResponse({"error": "Could not transcribe audio"}, status_code=400)
    
    return JSONResponse({"text": transcribed_text})


@router.post("/api/translate_audio")
async def translate_audio_endpoint(
    audio: UploadFile = File(...),
    target_language: str = Form("en"),
    source_language: str = Form("auto")
):
    """
    Transcribe audio using Whisper, then translate result to target language.
    Step 1: Whisper transcribes the audio
    Step 2: GPT translates the transcription to the target language
    """
    audio_bytes = await audio.read()
    
    # Step 1: Transcribe with Whisper
    transcribed_text = transcribe_audio_whisper(audio_bytes, filename=audio.filename or "audio.webm")
    
    if not transcribed_text:
        return JSONResponse({"error": "Could not transcribe audio"}, status_code=400)
    
    # Step 2: Translate the transcribed text
    def generate():
        # First send the transcription
        yield f"data: {json.dumps({'transcription': transcribed_text, 'chunk': ''})}\n\n"
        for chunk in translate_text_stream(
            text=transcribed_text,
            target_language=target_language,
            source_language=source_language
        ):
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )
