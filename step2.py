import json

from helper import call

# Groq free tier. It accepts one model, and this one supports strict JSON schema.
MODEL = "openai/gpt-oss-120b"

PROMPT = "Turn this voice note into a short video.\n\nVoice note: "

# The exact shape we want back. The model has to fill in these three fields.
SCHEMA = {
    "type": "object",
    "properties": {
        "script": {
            "type": "string",
            "description": "A 40 to 60 word voiceover, with audio tags like [excited] or [whispers]",
        },
        "image_prompt": {
            "type": "string",
            "description": "A detailed prompt for a 16:9 cover image",
        },
        "video_prompt": {
            "type": "string",
            "description": "An 8 second clip that starts on the cover image: describe the motion",
        },
    },
    "required": ["script", "image_prompt", "video_prompt"],
    "additionalProperties": False,
}


def write_script(text):
    data = call(
        "Script",
        "/chat/completions",
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": PROMPT + text}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "video_plan", "strict": True, "schema": SCHEMA},
            },
        },
    )
    return json.loads(data["choices"][0]["message"]["content"])


if __name__ == "__main__":
    with open("output/transcript.txt", encoding="utf-8") as transcript:
        text = transcript.read()
    script = write_script(text)
    print(json.dumps(script, indent=2))
    with open("output/script.json", "w", encoding="utf-8") as script_file:
        json.dump(script, script_file, indent=2)
