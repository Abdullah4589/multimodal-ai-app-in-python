import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
API = "https://api.groq.com/openai/v1"
HEADERS = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}
os.makedirs("output", exist_ok=True)

costs = {}  # running total: "step (model)" -> cost in USD


def post(path, payload):
    response = requests.post(API + path, headers=HEADERS, json=payload)
    if not response.ok:
        raise requests.HTTPError(response.text, response=response)
    return response


def add_cost(step, model, cost):
    costs[f"{step} ({model})"] = cost
    print(f"{step} ({model}): ${cost:.4f}")


def post_audio(path, model, file_path):
    """Upload an audio file. Groq transcriptions are multipart, not JSON."""
    with open(file_path, "rb") as audio_file:
        response = requests.post(
            API + path,
            headers=HEADERS,
            data={"model": model, "response_format": "json"},
            files={"file": (Path(file_path).name, audio_file, "audio/wav")},
        )
    if not response.ok:
        raise requests.HTTPError(response.text, response=response)
    return response


def call(step, path, payload):
    """Send a request and add its usage.cost to the running total."""
    data = post(path, payload).json()
    usage = data.get("usage") or {}
    add_cost(step, data.get("model", payload.get("model")), usage.get("cost", 0))
    return data


def lookup_cost(generation_id):
    """For responses with no JSON body (like audio), look the cost up by ID."""
    while True:
        response = requests.get(
            API + "/generation", headers=HEADERS, params={"id": generation_id}
        )
        if response.ok:
            return response.json()["data"]["total_cost"]
        time.sleep(2)  # takes a few seconds to show up
