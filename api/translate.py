# =====================================================
# Translation Agent - Module de traduction
# Utilise OpenAI Whisper pour audio et GPT pour texte
# =====================================================

import os
import json
import tempfile
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / '.env')

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Supported translation languages
SUPPORTED_LANGUAGES = {
    "fr": "French",
    "en": "English",
    "es": "Spanish",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "hi": "Hindi",
    "pl": "Polish",
    "tr": "Turkish",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
    "uk": "Ukrainian",
    "cs": "Czech",
    "ro": "Romanian",
    "el": "Greek",
    "he": "Hebrew",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
}


def load_translator_prompts(language: str = "en") -> tuple:
    """
    Load translator prompts from prompts.json file.
    
    Args:
        language: Language code ('en' or 'fr')
    
    Returns:
        tuple: (prompts dict for the specified language, model_config dict)
    """
    prompts_path = PROJECT_ROOT / "api/config" / "prompts.json"
    try:
        with open(prompts_path, 'r', encoding='utf-8') as f:
            prompts_data = json.load(f)
        
        # Extract model configuration
        model_config = {
            "name": prompts_data.get("model_name", "gpt-4o-mini")
        }
        
        lang_prompts = prompts_data.get(language, prompts_data.get("en", {}))
        return lang_prompts, model_config
    except FileNotFoundError:
        # Fallback to English defaults if file not found
        default_prompts = {
            "system_prompt": "You are a professional translator. {source_instruction} Translate the following text to {target_lang_name}. Provide ONLY the translation, no explanations, no notes, no original text. Maintain the original formatting, tone, and style. If the text is already in {target_lang_name}, return it as-is.",
            "auto_detect_instruction": "Auto-detect the source language.",
            "source_language_instruction": "The source language is {source_lang_name}."
        }
        default_model_config = {
            "name": "gpt-4o-mini"
        }
        return default_prompts, default_model_config


def translate_text_stream(text: str, target_language: str, source_language: str = "auto", prompt_language: str = "en"):
    """
    Translate text to target language using GPT-4o-mini with streaming.
    Uses Whisper-style translation approach through the OpenAI API.

    Args:
        text: The text to translate
        target_language: Target language code (e.g., 'fr', 'en', 'es')
        source_language: Source language code or 'auto' for auto-detection
        prompt_language: Language for the system prompt ('en' or 'fr')

    Yields:
        str: Translated text chunks
    """
    target_lang_name = SUPPORTED_LANGUAGES.get(target_language, target_language)
    source_lang_name = SUPPORTED_LANGUAGES.get(source_language, "auto-detect")

    # Load prompts and model config from JSON file
    prompts, model_config = load_translator_prompts(prompt_language)
    
    if source_language == "auto":
        source_instruction = prompts.get("auto_detect_instruction", "Auto-detect the source language.")
    else:
        source_instruction = prompts.get("source_language_instruction", "The source language is {source_lang_name}.").format(source_lang_name=source_lang_name)

    # Format system prompt with variables
    system_prompt = prompts.get("system_prompt", "").format(
        source_instruction=source_instruction,
        target_lang_name=target_lang_name
    )

    # Get model configuration
    model_name = model_config.get('name', 'gpt-4o-mini')
    
    # OpenAI streaming
    stream = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        stream=True,
        temperature=0.3,
    )

    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
                
  


def transcribe_audio_whisper(audio_bytes: bytes, filename: str = "audio.webm", language: str = None) -> str:
    """
    Transcribe audio using OpenAI Whisper API.

    Args:
        audio_bytes: Raw audio bytes
        filename: Original filename for format detection
        language: Optional ISO-639-1 language code (e.g., 'en', 'fr', 'es') for better accuracy

    Returns:
        str: Transcribed text
    """
    suffix = Path(filename).suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as audio_file:
            # Build transcription parameters
            params = {
                "model": "whisper-1",
                "file": audio_file,
                "response_format": "text"
            }
            # Add language parameter if specified
            if language:
                params["language"] = language
                print(f"Transcribing with language hint: {SUPPORTED_LANGUAGES.get(language, language)}")
            
            transcript = client.audio.transcriptions.create(**params)
        return transcript.strip()
    finally:
        os.unlink(tmp_path)


def translate_audio_whisper(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """
    Translate audio to English using OpenAI Whisper API translation endpoint.
    Whisper natively translates any language audio to English.

    Args:
        audio_bytes: Raw audio bytes
        filename: Original filename for format detection

    Returns:
        str: Translated English text
    """
    suffix = Path(filename).suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as audio_file:
            translation = client.audio.translations.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        return translation.strip()
    finally:
        os.unlink(tmp_path)


def get_supported_languages() -> dict:
    """Return the dictionary of supported languages."""
    return SUPPORTED_LANGUAGES
