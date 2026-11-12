import json
from urllib.parse import quote

import requests

from helper import add_cost

# Groq has no image route, and OpenRouter charges for image models.
# Pollinations Classic is free and needs no key (about 1 image per 45 seconds per IP).
MODEL = "pollinations"
IMAGE_API = "https://image.pollinations.ai/prompt/"


def make_image(script):
    prompt = script["image_prompt"]
    # Free tier keeps the aspect ratio but caps the area at 768x768.
    response = requests.get(
        IMAGE_API + quote(prompt),
        params={"width": 768, "height": 432, "seed": 42},
        timeout=180,
    )
    if response.status_code == 402:
        raise RuntimeError(
            "Free image limit reached (about 1 image every 45 seconds). Wait and run step3 again."
        )
    if not response.ok:
        raise requests.HTTPError(response.text[:500], response=response)
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        raise RuntimeError(
            f"Expected an image, got {content_type or 'unknown'}: {response.text[:300]}"
        )
    add_cost("Image", MODEL, 0)
    path = "output/cover.jpg"
    with open(path, "wb") as image_file:
        image_file.write(response.content)
    return path


if __name__ == "__main__":
    with open("output/script.json", encoding="utf-8") as script_file:
        script = json.load(script_file)
    print(make_image(script))
