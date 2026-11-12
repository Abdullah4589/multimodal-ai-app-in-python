# Multimodal AI App in Python

A small command-line app that turns a spoken idea into a short video package.

You talk into the microphone. The app transcribes the recording, asks a language model for a structured plan, draws a cover image, speaks a voiceover, and builds an eight-second zoom clip. At the end it prints a cost receipt for every paid call.

```
microphone
    │
    ▼
step1  record + transcribe          Groq Whisper
    │
    ▼
step2  script, image prompt,        Groq chat (strict JSON)
       video prompt
    │
    ├──────────────► step3  cover image     Pollinations (free)
    │
    └──────────────► step4  voiceover       Groq Orpheus, or Windows speech
                        │
                        ▼
                    step5  silent zoom clip  local, Windows only
                        │
                        ▼
                    cost receipt
```

The voiceover and the clip are separate files. Nothing in this version muxes them into one video with sound.

## What you get

| File | Produced by | Contents |
| --- | --- | --- |
| `output/idea.wav` | step 1 | 16 kHz mono recording |
| `output/transcript.txt` | step 1, only when run on its own | Plain transcript |
| `output/script.json` | step 2, only when run on its own | `script`, `image_prompt`, `video_prompt` |
| `output/cover.jpg` | step 3 | 768×432 cover image |
| `output/voiceover.wav` | step 4 | Spoken script |
| `output/clip.mp4` | step 5 | Silent 8-second zoom. The bytes are a Motion-JPEG AVI saved with an `.mp4` name |

`main.py` runs the whole pipeline and prints the receipt. It does not write `transcript.txt` or `script.json`. Those two files are written only when you run `step1.py` and `step2.py` directly.

## Requirements

- Windows 10 or 11. The zoom clip uses `System.Drawing`. The speech fallback uses `System.Speech`. Both are Windows APIs.
- Python 3.12 or newer.
- [uv](https://docs.astral.sh/uv/) for installing dependencies from the lockfile.
- A working microphone.
- A free [Groq](https://console.groq.com/) API key.
- Internet access for Groq and for the image service.

Linux and macOS can record, transcribe, write the script, and request an image. They cannot build the clip. They also cannot speak the script until Orpheus terms are accepted on the Groq account. See [Voiceover](#4-voiceover).

## Setup

From this folder:

```powershell
uv sync
copy .env.example .env
```

Open `.env` and set your key:

```
GROQ_API_KEY=gsk_your_key_here
```

`helper.py` loads that file on import. If the variable is missing, the process stops immediately with a `KeyError`.

The key is read from the environment only. It is listed in `.gitignore` and must not be committed.

One Groq model used here, Orpheus, needs a one-time terms acceptance in the Groq console before the API will return audio:

https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english

Until that is accepted, step 4 falls back to the Windows voice already installed on the machine (Microsoft Zira Desktop when that voice is present).

## Run the full pipeline

```powershell
uv run python main.py
```

1. Press Enter and start talking.
2. Press Enter again to stop.
3. Wait for transcription, the script, the image, the voiceover, and the clip.
4. Read the cost receipt printed at the end.

`main.py` runs those calls at import time. Importing it from another program starts a recording. Run it as a script.

Each step can also be run on its own, in order. Later steps read the files left by earlier ones:

```powershell
uv run python step1.py
uv run python step2.py
uv run python step3.py
uv run python step4.py
uv run python step5.py
```

`step3.py`, `step4.py`, and `step5.py` expect `output/script.json`. `step5.py` also expects `output/cover.jpg`.

The package entry point declared in `pyproject.toml` is a stub:

```powershell
uv run multimodal-ai-app-in-python
```

That command prints `Hello from multimodal-ai-app-in-python!` and does not run the pipeline. Use `uv run python main.py`.

## The five steps

### 1. Record and transcribe

`step1.py` opens the default input device at 16 kHz, mono, and appends chunks until you press Enter. It writes `output/idea.wav`, then uploads that WAV to Groq:

- Endpoint: `POST https://api.groq.com/openai/v1/audio/transcriptions`
- Model: `whisper-large-v3-turbo`
- The upload is multipart, not JSON.

The returned `text` is the transcript. Cost comes from `usage.cost` on the response. If Groq omits it, the line is `$0.0000`.

There is no maximum recording length, no silence detection, and no way to pass an existing WAV. A very long note will be uploaded in one request.

### 2. Write the video plan

`step2.py` sends the transcript to Groq chat completions with a strict JSON schema. The model must return exactly three strings:

| Field | What the prompt asks for |
| --- | --- |
| `script` | A 40 to 60 word voiceover. It may include tags such as `[excited]` or `[whispers]`. |
| `image_prompt` | A detailed prompt for a 16:9 cover. |
| `video_prompt` | Motion for an 8-second clip that starts on that cover. |

- Model: `openai/gpt-oss-120b`
- `response_format` is `json_schema` with `strict: true`
- Extra properties are rejected by the schema

The user message is fixed: `Turn this voice note into a short video.` plus the transcript. There is no system prompt and no second pass.

Cost comes from `usage.cost`.

### 3. Cover image

Groq has no image route in this app. `step3.py` calls Pollinations Classic, which needs no key:

```
GET https://image.pollinations.ai/prompt/{url-encoded image_prompt}
    ?width=768&height=432&seed=42
```

The free tier keeps the aspect ratio and caps the area near 768×768, so the request asks for 768×432. The seed is always `42`, so the same prompt tends to return a similar picture.

The response must have a `Content-Type` starting with `image/`. Anything else is treated as an error. HTTP 402 is reported as the free-tier limit, about one image every 45 seconds per IP. The call is recorded as `$0.0000`.

The image prompt is sent to a third-party public service. Do not put secrets or private details in the spoken idea if you do not want them in that prompt.

### 4. Voiceover

`step4.py` tries Groq Orpheus first.

- Model: `canopylabs/orpheus-v1-english`
- Voice: `troy`
- Format: WAV
- Input limit handled here: 200 characters per request

A 40–60 word script is usually longer than 200 characters, so the text is split on sentence boundaries, then on words if one sentence is still too long. The WAV pieces are concatenated in order.

Orpheus treats bracket tags as vocal directions. The Windows fallback does not, so those tags are stripped before Windows speaks, otherwise the voice would read the word "excited" aloud.

If Groq returns `model_terms_required`, the app prints the console link and uses Windows speech at `$0.0000`. Any other HTTP error is raised.

The speech response is raw audio and has no `usage` object. The Orpheus line on the receipt is an estimate: `$22` per 1,000,000 characters, counted on the chunks that were sent. It is not a bill retrieved from Groq. `helper.lookup_cost` can ask Groq for a generation cost by id, and this step does not call it.

On a non-Windows machine, a terms error stops the step. There is no other fallback.

### 5. Clip

`step5.py` does not call a video model. The comment in the file states that Groq has no video route and that there is no video key in `.env`.

What it does instead, on Windows only:

1. Require `script["video_prompt"]` to be present. The text is not sent anywhere. It is only checked.
2. Load `output/cover.jpg`.
3. Use PowerShell and `System.Drawing` to crop and scale the image into 64 JPEG frames (8 seconds × 8 fps). The crop tightens by up to 12 percent, which reads as a slow zoom in.
4. Pack those frames into a Motion-JPEG AVI and save it as `output/clip.mp4`.

Windows Media Player can open that file. Players that only accept a real MP4 container may not. The file has no audio track. Cost is `$0.0000` and the model name on the receipt is `windows`.

## Cost receipt

`helper.costs` is a dict filled as each step finishes. `main.py` prints it once:

```
COST RECEIPT
Transcribe (whisper-large-v3-turbo)                    $0.0003
Script (openai/gpt-oss-120b)                           $0.0012
Image (pollinations)                                   $0.0000
Voiceover (windows)                                    $0.0000
Video (windows)                                        $0.0000
TOTAL                                                  $0.0015
```

Numbers above are an illustration. Real Whisper and chat costs depend on audio length, token use, and Groq's current prices. Image, Windows voiceover, and the local clip are always zero in this code.

Costs are kept in memory for one process. They are not written to disk. Running a single step prints only that step's line, because the receipt lives in `main.py`.

## Project layout

```
main.py                  Runs steps 1–5 and prints the receipt
helper.py                Groq HTTP helpers, .env loading, cost map
step1.py                 Microphone recording and Whisper
step2.py                 JSON video plan
step3.py                 Pollinations cover image
step4.py                 Orpheus voiceover, Windows fallback
step5.py                 Local zoom clip
src/multimodal_ai_app_in_python/__init__.py
                         Stub console-script entry point
pyproject.toml           Project metadata and dependencies
uv.lock                  Locked dependency versions
.env.example             Variable name only. Copy to .env
output/                  Created at runtime. Gitignored
```

Runtime dependencies are `numpy`, `python-dotenv`, `requests`, `sounddevice`, and `soundfile`. There is no local model runtime and no PyTorch install.

## Configuration

| Name | Where | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | `.env` | Bearer token for every Groq call |

Everything else is a constant in the step file: model ids, Orpheus voice, image size, seed, clip length, and frame rate. Changing them means editing those files.

## Plus points

- The path from speech to picture, voice, and clip is visible in five short modules. You can run one step, inspect its file, and continue.
- The language-model call uses a strict JSON schema, so later steps read named fields instead of scraping free text.
- Paid work stays on Groq's hosted API. Image generation, the Windows voice, and the zoom clip add no model charge in this code.
- If Orpheus terms are not accepted yet, Windows speech still produces a voiceover instead of failing the whole run.
- Each Groq call records a cost as it returns, and the full run ends with a total.
- Dependencies stay small. Audio I/O, HTTP, and dotenv are enough for the hosted models.
- Recording, upload, schema, chunking, and the AVI writer are ordinary Python. There is no framework to learn before changing a step.
- The image client checks status and content type, and it explains the free-tier 402 instead of saving an error page as `cover.jpg`.

## Limitations

- The clip does not follow `video_prompt`. That field is required and then ignored. Motion is always the same 12 percent zoom.
- `clip.mp4` is silent. The voiceover stays in `output/voiceover.wav`. The extension says MP4, but the container is Motion-JPEG AVI.
- Eight frames per second is enough to see the zoom and too low to look like normal video.
- Video frames and the speech fallback require Windows. Other systems stop at those steps.
- `main.py` starts recording as soon as it is loaded, and it does not save the transcript or the script JSON.
- The console script installed by the package does not call `main.py`.
- There is no CLI. You cannot pass a WAV, a text idea, an output folder, or a model name.
- A missing `GROQ_API_KEY` raises `KeyError` during import, before any instruction is printed.
- The same image seed is used every time. Repeated prompts look alike, and you cannot ask for a new variation without editing `step3.py`.
- Pollinations is a public service with its own rate limit and content rules. A 402 or a slow response blocks the pipeline. Prompts leave your machine.
- Orpheus audio is split at 200 characters. A sentence can be cut, and the estimated character price can disagree with the Groq dashboard.
- Bracket directions such as `[excited]` only affect Orpheus. The Windows voice speaks the plain sentence.
- `lookup_cost` is unused. Speech billing is estimated. Other steps trust `usage.cost` and store `0` when it is absent.
- Failed runs leave partial files in `output/`. Nothing rolls them back.
- There are no tests, no type checker config, and no retry around network calls except the message on image HTTP 402.
- Microphone errors, an empty recording, and a JSON response that fails `json.loads` are uncaught.
- `pyproject.toml` still has the placeholder description `Add your description here`.

## What can be improved

Highest value first:

1. **Mux the voiceover into a real MP4.** Use ffmpeg or a similar tool to combine `cover.jpg` or the zoom frames with `voiceover.wav`, and write an actual MPEG-4 file. The current player compatibility problem and the silent clip go away together.
2. **Use `video_prompt` or stop asking for it.** A still zoom should be labeled as a Ken Burns clip. If a video model is added later, keep the Windows zoom as the fallback when no video key is set.
3. **Make `main.py` a real program.** Put the pipeline under `if __name__ == "__main__"`. Save `transcript.txt` and `script.json` on the full run. Point the `multimodal-ai-app-in-python` script at that function.
4. **Accept a file or typed text.** `--wav`, `--text`, and `--out` would let you rerun from the transcript without another take, and would make the steps testable.
5. **Fail clearly on setup.** Check `GROQ_API_KEY` once and print that `.env` is missing. Check for a microphone before recording. Check that `output/script.json` exists before steps 3–5.
6. **Cross-platform picture and speech.** Pillow can build the zoom frames without PowerShell. A second hosted voice, or an offline voice, would cover machines that are not Windows.
7. **Retrieve speech cost by generation id.** `lookup_cost` already polls `/generation`. Wiring it to the Orpheus response would replace the hardcoded `$22 / 1_000_000` estimate.
8. **Vary the image.** Accept a seed, width, and height. Retry 402 with a short wait. Document that prompts are sent to Pollinations, and skip the call when a cover file is already present.
9. **Tests for the pure functions.** `speech_chunks`, JPEG size parsing, and the AVI writer do not need a microphone or an API key. A schema fixture would lock the three script fields.
10. **Richer clip.** Higher frame rate, a slight pan, burned-in captions from the script, and background music are all local changes. They still would not be the motion described by the model.
11. **Config file.** Move model names, voice, prices, and durations out of the modules so a free-tier model swap does not require a code edit.
12. **Package metadata.** Replace the placeholder description, and add a license if the repo should be reusable by others.

## Troubleshooting

| What you see | What it usually means |
| --- | --- |
| `KeyError: 'GROQ_API_KEY'` | `.env` is missing or the variable name is wrong. Copy `.env.example` and set the key. |
| Recording never starts, or sounddevice raises | No default input device, or the microphone is in use. Close other apps using the mic and try again. |
| HTTP 401 or 403 from Groq | The key is invalid, expired, or not allowed to call that model. |
| Message containing `model_terms_required` | Open the Orpheus playground link once and accept terms. Until then, Windows speech is used. |
| `Free image limit reached` | Pollinations returned 402. Wait about 45 seconds and run `step3.py` again. |
| `Expected an image, got ...` | The image service returned text. The body snippet is printed. Retry later. |
| `This clip is drawn with the Windows image API.` | `step5.py` was started on a non-Windows system. |
| A player will not open `clip.mp4` | The file is Motion-JPEG AVI. Open it in Windows Media Player, or remux it. |
| The clip has no sound | Expected. Play `output/voiceover.wav` beside it. |
| `Hello from multimodal-ai-app-in-python!` | The stub entry point ran. Use `uv run python main.py`. |

## Privacy

- The microphone capture stays in `output/idea.wav` on this machine until you delete it.
- The recording and the transcript are sent to Groq.
- The image prompt, which the model writes from your words, is sent to Pollinations.
- The script text is sent to Groq again when Orpheus is used.
- `.env` is gitignored. Do not paste the API key into issues, commits, or the spoken note.

## Author

Abdullah. Project metadata in `pyproject.toml` uses that name.

This repository has no license file. The code is public to read. Reuse needs the author's permission until a license is added.
