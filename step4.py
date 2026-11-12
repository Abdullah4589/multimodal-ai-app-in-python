import io
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

from helper import add_cost, post

# Groq hosts Orpheus, not Gemini TTS. The reply is a WAV, and [excited] is a vocal direction.
# This account still has to accept Orpheus terms once in the Groq console, so until then
# the voiceover is spoken by the Windows voice that is already installed.
MODEL = "canopylabs/orpheus-v1-english"
VOICE = "troy"
MAX_CHARS = 200
TERMS_URL = "https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english"
# Listed price. The speech response is audio, so it has no usage object to read.
CHAR_USD = 22 / 1_000_000


def speech_chunks(text, limit=MAX_CHARS):
    """Split on sentences. A 40–60 word script is longer than Orpheus allows."""
    text = " ".join(text.split())
    if not text:
        raise ValueError("Script is empty.")
    if len(text) <= limit:
        return [text]

    chunks = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if len(sentence) > limit:
            if current:
                chunks.append(current)
                current = ""
            line = ""
            for word in sentence.split():
                nxt = word if not line else f"{line} {word}"
                if len(nxt) <= limit:
                    line = nxt
                    continue
                if line:
                    chunks.append(line)
                line = word[:limit]
            current = line
            continue
        nxt = sentence if not current else f"{current} {sentence}"
        if len(nxt) <= limit:
            current = nxt
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def speak_orpheus(text):
    pieces = []
    sample_rate = None
    spoken = 0
    for chunk in speech_chunks(text):
        response = post(
            "/audio/speech",
            {
                "model": MODEL,
                "input": chunk,
                "voice": VOICE,
                "response_format": "wav",
            },
        )
        if response.content[:4] != b"RIFF":
            raise RuntimeError(
                f"Expected a WAV file, got {response.headers.get('content-type', 'unknown')}"
            )
        audio, sample_rate = sf.read(io.BytesIO(response.content), dtype="int16")
        pieces.append(audio)
        spoken += len(chunk)

    path = "output/voiceover.wav"
    sf.write(path, np.concatenate(pieces), sample_rate)
    add_cost("Voiceover", MODEL, spoken * CHAR_USD)
    return path


def plain_speech(text):
    """Windows reads bracket tags aloud. Orpheus treats them as directions."""
    return " ".join(re.sub(r"\[[^\]]*\]", " ", text).split())


def speak_windows(text):
    if os.name != "nt":
        raise RuntimeError(f"Accept the Orpheus terms once, then run this again: {TERMS_URL}")
    path = Path("output/voiceover.wav").resolve()
    ps = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$wanted = 'Microsoft Zira Desktop'
$names = @($synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name })
if ($names -contains $wanted) { $synth.SelectVoice($wanted) }
$synth.SetOutputToWaveFile($env:VOICE_PATH)
$synth.Speak([Console]::In.ReadToEnd())
$synth.Dispose()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        input=plain_speech(text),
        text=True,
        check=True,
        env={**os.environ, "VOICE_PATH": str(path)},
    )
    add_cost("Voiceover", "windows", 0)
    return "output/voiceover.wav"


def speak(script):
    text = script["script"]
    try:
        return speak_orpheus(text)
    except requests.HTTPError as exc:
        body = exc.response.text if exc.response is not None else ""
        if "model_terms_required" not in body:
            raise
    print(f"Orpheus needs a one-time terms acceptance: {TERMS_URL}")
    print("Using the Windows voice until then.")
    return speak_windows(text)


if __name__ == "__main__":
    with open("output/script.json", encoding="utf-8") as script_file:
        script = json.load(script_file)
    print(speak(script))
