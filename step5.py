import json
import os
import struct
import subprocess
import tempfile
from pathlib import Path

from helper import add_cost

# Groq has no video route, and Veo is paid. There is no video key in .env.
# Hold the cover for 8 seconds and zoom in slightly, which is the motion the prompt starts with.
MODEL = "windows"
SECONDS = 8
FPS = 8


def jpeg_size(data):
    index = 2
    while index < len(data) - 8:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        length = int.from_bytes(data[index + 2 : index + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2):
            height = int.from_bytes(data[index + 5 : index + 7], "big")
            width = int.from_bytes(data[index + 7 : index + 9], "big")
            return width, height
        index += 2 + length
    raise ValueError("Could not read the JPEG size.")


def write_clip(path, frames, fps):
    """Motion-JPEG video. Windows Media Player opens this file."""
    width, height = jpeg_size(frames[0])
    if any(jpeg_size(frame) != (width, height) for frame in frames):
        raise ValueError("Zoomed frames are not the same size.")

    def u32(value):
        return struct.pack("<I", value)

    def chunk(tag, payload):
        pad = b"\x00" if len(payload) % 2 else b""
        return tag + u32(len(payload)) + payload + pad

    def list_chunk(kind, payload):
        body = kind + payload
        return b"LIST" + u32(len(body)) + body

    max_frame = max(len(frame) for frame in frames)
    header = struct.pack(
        "<14I",
        int(1_000_000 / fps),
        max_frame * fps,
        0,
        0x110,
        len(frames),
        0,
        1,
        max_frame,
        width,
        height,
        0,
        0,
        0,
        0,
    )
    stream = b"".join(
        [
            b"vids",
            b"MJPG",
            u32(0),
            struct.pack("<HH", 0, 0),
            u32(0),
            u32(1),
            u32(fps),
            u32(0),
            u32(len(frames)),
            u32(max_frame),
            u32(0xFFFFFFFF),
            u32(0),
            struct.pack("<hhhh", 0, 0, width, height),
        ]
    )
    bitmap = struct.pack(
        "<IiiHH4sIiiII",
        40,
        width,
        height,
        1,
        24,
        b"MJPG",
        width * height * 3,
        0,
        0,
        0,
        0,
    )
    hdrl = list_chunk(
        b"hdrl",
        chunk(b"avih", header)
        + list_chunk(b"strl", chunk(b"strh", stream) + chunk(b"strf", bitmap)),
    )

    movi_body = bytearray(b"movi")
    index = bytearray()
    for frame in frames:
        offset = len(movi_body)
        payload = frame + (b"\x00" if len(frame) % 2 else b"")
        movi_body += b"00dc" + u32(len(frame)) + payload
        index += b"00dc" + u32(0x10) + u32(offset) + u32(len(frame))
    movi = b"LIST" + u32(len(movi_body)) + bytes(movi_body)
    body = b"AVI " + hdrl + movi + chunk(b"idx1", bytes(index))
    Path(path).write_bytes(b"RIFF" + u32(len(body)) + body)


def zoom_frames(image_path, count):
    if os.name != "nt":
        raise RuntimeError("This clip is drawn with the Windows image API.")
    folder = Path(tempfile.mkdtemp(prefix="clip-frames-"))
    ps = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$src = [System.Drawing.Image]::FromFile($env:COVER_PATH)
$w = $src.Width
$h = $src.Height
$n = [int]$env:FRAME_COUNT
for ($i = 0; $i -lt $n; $i++) {
    $zoom = 1.0 + (0.12 * $i / [Math]::Max($n - 1, 1))
    $cw = [Math]::Max([int]($w / $zoom), 1)
    $ch = [Math]::Max([int]($h / $zoom), 1)
    $x = [int](($w - $cw) / 2)
    $y = [int](($h - $ch) / 2)
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $graphics = [System.Drawing.Graphics]::FromImage($bmp)
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $dest = New-Object System.Drawing.Rectangle 0, 0, $w, $h
    $srcRect = New-Object System.Drawing.Rectangle $x, $y, $cw, $ch
    $graphics.DrawImage($src, $dest, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
    $graphics.Dispose()
    $bmp.Save((Join-Path $env:FRAME_DIR ('{0:D3}.jpg' -f $i)), [System.Drawing.Imaging.ImageFormat]::Jpeg)
    $bmp.Dispose()
}
$src.Dispose()
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=True,
            env={
                **os.environ,
                "COVER_PATH": str(Path(image_path).resolve()),
                "FRAME_DIR": str(folder),
                "FRAME_COUNT": str(count),
            },
        )
        frames = [path.read_bytes() for path in sorted(folder.glob("*.jpg"))]
    finally:
        for path in folder.glob("*"):
            path.unlink()
        folder.rmdir()
    if len(frames) != count:
        raise RuntimeError(f"Expected {count} frames, got {len(frames)}.")
    return frames


def make_video(script, image_path):
    if not script.get("video_prompt"):
        raise ValueError("Script is missing video_prompt.")
    if not Path(image_path).is_file():
        raise FileNotFoundError(f"Cover image not found: {image_path}. Run step3 first.")
    path = "output/clip.mp4"
    write_clip(path, zoom_frames(image_path, SECONDS * FPS), FPS)
    add_cost("Video", MODEL, 0)
    return path


if __name__ == "__main__":
    with open("output/script.json", encoding="utf-8") as script_file:
        script = json.load(script_file)
    print(make_video(script, "output/cover.jpg"))
