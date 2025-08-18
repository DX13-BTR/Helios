from fastapi import APIRouter, Response
from pydantic import BaseModel
from google.cloud import texttospeech
import hashlib
import asyncio

router = APIRouter()

# Map your tones to Google voices (adjust to taste / availability in your project)
TONE_TO_VOICE = {
    "gentle":    "en-GB-Wavenet-C",
    "assertive": "en-GB-Wavenet-B",
    "neutral":   "en-GB-Wavenet-A",
    "urgent":    "en-GB-Wavenet-D",
}

class SpeakRequest(BaseModel):
    text: str
    tone: str = "neutral"
    speaking_rate: float = 1.0
    pitch: float = 0.0

# Simple in-memory cache to avoid re-synthesizing identical requests
_cache: dict[str, bytes] = {}

def _cache_key(req: SpeakRequest) -> str:
    h = hashlib.sha256()
    h.update(req.text.encode("utf-8"))
    h.update(req.tone.encode("utf-8"))
    h.update(str(req.speaking_rate).encode("utf-8"))
    h.update(str(req.pitch).encode("utf-8"))
    return h.hexdigest()

@router.post("/speak")
async def speak(req: SpeakRequest):
    """
    POST /api/voice/speak
    Body: { "text": "...", "tone": "neutral|gentle|assertive|urgent", "speaking_rate": 1.0, "pitch": 0.0 }
    Returns: MP3 audio bytes
    """
    key = _cache_key(req)
    if key in _cache:
        return Response(content=_cache[key], media_type="audio/mpeg")

    client = texttospeech.TextToSpeechClient()

    # Build synthesis request
    input_ = texttospeech.SynthesisInput(text=req.text)
    voice_name = TONE_TO_VOICE.get(req.tone, TONE_TO_VOICE["neutral"])
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-GB",
        name=voice_name,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=req.speaking_rate,
        pitch=req.pitch,
    )

    # Google SDK is sync; run in a thread so we don't block the event loop
    def _synth():
        return client.synthesize_speech(
            input=input_, voice=voice, audio_config=audio_config
        ).audio_content

    audio_content = await asyncio.to_thread(_synth)
    _cache[key] = audio_content
    return Response(content=audio_content, media_type="audio/mpeg")
