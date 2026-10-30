#!/usr/bin/env python3

"""
Morning Report — Doomscrolling Bedside Companion

Reads phone-absence events from the YOLO detector.
Uses Python for accurate statistics and factual reporting.
Uses Qwen for a playful closing sentence.
Uses Piper TTS to speak the complete report.

Compatible with bedside_controller.py.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests

# Fix Unicode output over SSH
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace"
    )

BASE_DIR = Path(__file__).resolve().parent

VOICE_MODEL = (
    Path.home()
    / "Documents/GitHub/Interactive-Lab-Hub/Lab 3"
    / "speech-scripts/en_US-lessac-medium.onnx"
)

# ----------------------------------------
# ARGUMENTS
# ----------------------------------------

parser = argparse.ArgumentParser()

parser.add_argument(
    "--log",
    default="doomscroll_log.jsonl"
)

parser.add_argument(
    "--model",
    default="qwen3.5:0.8b"
)

parser.add_argument(
    "--voice-model",
    default=str(VOICE_MODEL)
)

parser.add_argument(
    "--wav-out",
    default=str(BASE_DIR / "morning_report.wav")
)

args = parser.parse_args()

# ----------------------------------------
# READ JSONL
# ----------------------------------------

with open(args.log, encoding="utf-8") as f:
    entries = [
        json.loads(line)
        for line in f
        if line.strip()
    ]

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

# ----------------------------------------
# VERIFIED STATISTICS
# ----------------------------------------

print(
    f"Phone-away sessions: {len(sessions)}",
    flush=True
)

print(
    f"Total phone-away time: {total_minutes:.1f} minutes",
    flush=True
)

print(
    f"Possible doomscrolling sessions: "
    f"{len(doomscroll_sessions)}",
    flush=True
)

# ----------------------------------------
# FORMAT THE FACTUAL REPORT
# ----------------------------------------

def describe_minutes(minutes):
    if minutes < 1:
        return f"about {round(minutes * 60)} seconds"

    return f"about {minutes:.1f} minutes"


def format_time(epoch):
    return datetime.fromtimestamp(
        float(epoch)
    ).strftime("%I:%M %p")


if not sessions:
    factual_report = (
        "Good morning! "
        "No completed phone-away sessions "
        "were recorded last night."
    )

else:
    count = len(sessions)
    total_text = describe_minutes(total_minutes)

    sentence_1 = (
        f"Good morning! Your phone was away "
        f"from its resting spot {count} "
        f"{'time' if count == 1 else 'times'} "
        f"last night, for a total of {total_text}."
    )

    doom_count = len(doomscroll_sessions)

    if doom_count == 0:
        sentence_2 = (
            "None of those sessions crossed "
            "the threshold for possible doomscrolling."
        )

    elif doom_count == 1:
        sentence_2 = (
            "One of those sessions crossed "
            "the threshold for possible doomscrolling."
        )

    else:
        sentence_2 = (
            f"{doom_count} of those sessions crossed "
            "the threshold for possible doomscrolling."
        )

    factual_report = (
        sentence_1 + " " + sentence_2
    )

# ----------------------------------------
# QWEN: GENERATE ONLY THE FINAL SENTENCE
# ----------------------------------------

if sessions:
    longest = max(
        sessions,
        key=lambda e: float(
            e.get("duration_minutes", 0)
        )
    )

    longest_minutes = float(
        longest.get("duration_minutes", 0)
    )

    context = (
        f"Total phone-away sessions: {len(sessions)}\n"
        f"Total time away: {total_minutes:.1f} minutes\n"
        f"Above-threshold sessions: "
        f"{len(doomscroll_sessions)}\n"
        f"Longest session: {longest_minutes:.1f} minutes\n"
        f"Longest session started at: "
        f"{format_time(longest['start_epoch'])}"
    )

    prompt = f"""
You are a friendly, playful bedside companion.

A camera watches a phone's resting spot.
Time away from that spot is only a possible
indicator of phone use, not proof of scrolling.

Verified facts:
{context}

The first two sentences of the morning report
have already been written accurately.

Your task:
Write ONLY ONE additional short sentence
to end the report in a warm, slightly playful way.

Rules:
- Do not repeat or change any statistics.
- Do not claim actual scrolling was observed.
- Do not invent events or emotions.
- Do not give health advice.
- Avoid judgmental language.
- Do not use emojis or markdown.
- Output exactly one sentence.
"""

    print(
        "\n[QWEN] Generating playful closing...",
        flush=True
    )

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": args.model,
                "prompt": prompt,
                "think": False,
                "stream": False,
                "options": {
                    "num_ctx": 4096,
                    "temperature": 0.3,
                    "num_predict": 80
                }
            },
            timeout=600
        )

        response.raise_for_status()

        closing = response.json().get(
            "response", ""
        ).strip()

        # Remove newlines, emojis and stray quotes.
        closing = re.sub(r"\s+", " ", closing)
        closing = re.sub(
            r"[\U00010000-\U0010ffff]",
            "",
            closing
        ).strip(' "\'')

        # A very small model may ignore instructions.
        # Reject the closing if it contains more than
        # one sentence or obvious unsupported claims.
        sentences = re.split(
            r"(?<=[.!?])\s+",
            closing
        )

        if (
            not closing
            or len(sentences) != 1
            or len(closing) > 180
            or re.search(
                r"\b(no sessions?|none|zero|"
                r"never|definitely|certainly|"
                r"you were scrolling|you scrolled)\b",
                closing,
                re.IGNORECASE
            )
        ):
            raise ValueError(
                "Qwen produced an unsuitable closing."
            )

    except (
        requests.RequestException,
        ValueError,
        KeyError
    ) as error:
        print(
            f"[QWEN] Using fallback closing: {error}",
            flush=True
        )

        closing = (
            "Your little bedside companion "
            "will be here again tonight!"
        )

else:
    closing = (
        "Your little bedside companion "
        "will be here again tonight!"
    )

# ----------------------------------------
# FINAL MORNING REPORT
# ----------------------------------------

report = factual_report + " " + closing

print("\nMorning Report:\n", flush=True)
print(report, flush=True)

# Save the report as text
report_path = BASE_DIR / "morning_report.txt"

report_path.write_text(
    report + "\n",
    encoding="utf-8"
)

# ----------------------------------------
# PIPER TEXT-TO-SPEECH
# ----------------------------------------

speech_text = re.sub(
    r"[\U00010000-\U0010ffff]",
    "",
    report
)

print(
    "\n[PIPER] Generating speech...",
    flush=True
)

subprocess.run(
    [
        "piper",
        "--model",
        args.voice_model,
        "--output_file",
        args.wav_out
    ],
    input=speech_text.encode("utf-8"),
    check=True
)

# ----------------------------------------
# AUDIO PLAYBACK
# ----------------------------------------

print(
    "[AUDIO] Playing morning report...",
    flush=True
)

subprocess.run(
    ["aplay", args.wav_out],
    check=True
)

print(
    "[DONE] Morning report finished.",
    flush=True
)
