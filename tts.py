"""Text-to-speech for the spoken tour + the voiced Guide (the "demo lady").

This is the ONE place the rig touches OpenAI, and ONLY for VOICE -- a cosmetic layer, ~half a cent per
clip, never the brain (the brain stays on AI Core). It is OFF unless RIG_TTS is on AND an OpenAI key is
present, with a hard kill-switch. Clips are CACHED by (voice, text) to disk, so the fixed tour costs a
few cents once and is free forever after; only genuinely new lines (the Guide's dynamic answers) cost.

    synth(text[, voice]) -> base64 mp3, or "" (off / no key / failure -> caller falls back to captions).
"""
import os
import re
import base64
import hashlib
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()                                  # so OPENAI_API_KEY (voice only) is available
except Exception:
    pass

# Voice is on only when explicitly enabled -- honours "AI Core only" by default; flip RIG_TTS=on for demos.
TTS_ON = os.getenv("RIG_TTS", "off").lower() in ("1", "on", "true", "yes")
TTS_VOICE = os.getenv("TOUR_VOICE", "nova")        # the warm female voice
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")        # tts-1 (fast/cheap) or tts-1-hd

_DIR = Path(__file__).resolve().parent / "tts_cache"
_MEM: dict[str, str] = {}                          # (voice,text) sha1 -> b64, this run
_client = None


def _key(voice: str, text: str) -> str:
    return hashlib.sha1(f"{voice}|{text}".encode("utf-8")).hexdigest()


def _oai():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI()                         # OPENAI_API_KEY from env (voice only)
    return _client


# Spoken-form fixes: things the voice mispronounces. "SAP" must be said as letters (S-A-P), not "sap"
# like tree sap. Applied to the TTS INPUT only -- on-screen captions still show "SAP".
def _say(text: str) -> str:
    return re.sub(r"\bSAP\b", "ess ay pee", text)


def synth(text: str, voice: str = None) -> str:
    """base64 mp3 for `text` (cached). Returns '' when TTS is off, there's no key, or it fails -- the
    caller then falls back to on-screen captions for that line."""
    text = _say((text or "").strip())[:800]
    if not text or not TTS_ON:
        return ""
    voice = voice or TTS_VOICE
    k = _key(voice, text)
    if k in _MEM:                                  # hot cache
        return _MEM[k]
    fp = _DIR / f"{k}.mp3"
    try:                                           # warm (disk) cache -> deterministic + free across runs
        if fp.exists():
            b = base64.b64encode(fp.read_bytes()).decode()
            _MEM[k] = b
            return b
    except Exception:
        pass
    try:
        sp = _oai().audio.speech.create(model=TTS_MODEL, voice=voice, input=text)
        b = base64.b64encode(sp.content).decode()
        _MEM[k] = b
        try:
            _DIR.mkdir(exist_ok=True)
            fp.write_bytes(sp.content)
        except Exception:
            pass
        return b
    except Exception:
        return ""
