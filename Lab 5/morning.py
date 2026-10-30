#!/usr/bin/env python3

"""
Morning report for phone-resting-spot detection.

Reads absence events from the detector's JSONL file,
generates a report with Ollama/Qwen, and speaks it with Piper.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_VOICE = (
    Path.home()
    / "Documents/GitHub/Interactive-Lab-Hub/Lab 3"
    / "speech-scripts/en_US-lessac-medium.onnx"
)

parser = argparse.ArgumentParser()
parser.add_argument("--log", default="doomscroll_log.jsonl")
parser.add_argument("--model", default="qwen3.5:0.8b")
parser.add_argument("--voice-model", default=str(DEFAULT_VOICE))
parser.add_argument("--wav-out", default=str(BASE_DIR / "morning_report.wav"))
args = parser.parse_args()

# Read the detector log
with open(args.log, encoding="utf-8") as f:
    entries = [
        json.loads(line)
        for line in f
        if line.strip()
    ]

# Each completed absence event represents one time
# the phone was away from its resting spot.
sessions = [
    e for e in entries
    if e.get("event") == "phone_absence_end"
]

total_minutes = sum(
    float(e.get("duration_minutes", 0))
    for e in sessions
)

doomscroll_sessions = [
    e for e in sessions
    if e.get("doomscrolling", False)
]

def format_time(epoch):
    return datetime.fromtimestamp(
        float(epoch)
    ).strftime("%I:%M %p")

print(f"Phone-away sessions: {len(sessions)}")
print(f"Total phone-away time: {total_minutes:.1f} minutes")
print(f"Possible doomscrolling sessions: {len(doomscroll_sessions)}")

if sessions:
    digest = "\n".join(
        f"Phone away from {format_time(e['start_epoch'])} "
        f"to {format_time(e['end_epoch'])}, "
        f"duration {float(e['duration_minutes']):.1f} minutes, "
        f"above threshold: {e.get('doomscrolling', False)}"
        for e in sessions
    )

    prompt = f"""
You are a warm, playful bedside companion.

A webcam watches a phone's resting spot.
When the phone disappears, the device records how
long it remains away.

Phone absence is only a possible indicator of
phone use. It does not prove that someone
was scrolling.

Here is the recorded data:

{digest}

Total phone-away time: {total_minutes:.1f} minutes.
Sessions exceeding the configured threshold:
{len(doomscroll_sessions)}.

Write exactly three short sentences for a spoken
morning report.

Mention:
- Total time away from the resting spot
- Whether any absence sessions exceeded the threshold
- One interesting observation supported by the data

Use a warm, slightly playful tone.
Do not invent events.
Do not claim scrolling was directly observed.
Do not use emojis, markdown, or bullet points.
"""

    print("[QWEN] Generating morning report...", flush=True)

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": args.model,
            "prompt": prompt,
            "think": False,
            "stream": False,
            "options": {
                "num_ctx": 4096,
                "temperature": 0.3
            }
        },
        timeout=600
    )

    response.raise_for_status()
    report = response.json()["response"].strip()

else:
    report = (
        "Good morning! No completed phone-away "
        "sessions were recorded. Your phone's "
        "resting spot had a quiet night."
    )

print("\nMorning Report:\n")
print(report, flush=True)

# Save the text version
report_path = BASE_DIR / "morning_report.txt"
report_path.write_text(report + "\n", encoding="utf-8")

# Remove unusual characters before speaking
speech_text = re.sub(r"[\U00010000-\U0010ffff]", "", report)

# Generate voice audio
print("\n[PIPER] Generating speech...", flush=True)

subprocess.run(
    [
        "piper",
        "--model", args.voice_model,
        "--output_file", args.wav_out
    ],
    input=speech_text.encode("utf-8"),
    check=True
)

# Play through Raspberry Pi speaker
print("[AUDIO] Playing morning report...", flush=True)

subprocess.run(
    ["aplay", args.wav_out],
    check=True
)

print("[DONE] Morning report finished.", flush=True)
PYTHON
