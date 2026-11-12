import numpy as np
import sounddevice as sd
import soundfile as sf

from helper import add_cost, post_audio

MODEL = "whisper-large-v3-turbo"
RATE = 16000  # samples per second, plenty for speech


def record(path="output/idea.wav"):
    chunks = []
    input("Press Enter and start talking...")
    # Collect audio from the mic until Enter is pressed again
    with sd.InputStream(
        samplerate=RATE,
        channels=1,
        callback=lambda data, *_: chunks.append(data.copy()),
    ):
        input("Recording! Press Enter to stop.")
    sf.write(path, np.concatenate(chunks), RATE)
    return path


def transcribe(path):
    data = post_audio("/audio/transcriptions", MODEL, path).json()
    add_cost("Transcribe", MODEL, (data.get("usage") or {}).get("cost", 0))
    return data["text"]


if __name__ == "__main__":
    path = record()
    text = transcribe(path)
    print(text)
    with open("output/transcript.txt", "w", encoding="utf-8") as transcript:
        transcript.write(text)
