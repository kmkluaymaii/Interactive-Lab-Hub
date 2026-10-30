
import argparse
import json
from datetime import datetime

import requests

parser = argparse.ArgumentParser()
parser.add_argument("--log", default="doomscroll_log.jsonl")
parser.add_argument("--model", default="qwen3.5:0.8b")
args = parser.parse_args()

with open(args.log, encoding="utf-8") as f:
    entries = [json.loads(line) for line in f if line.strip()]

# Select completed phone sessions
sessions = [
    e for e in entries
    if e.get("event") == "phone_session_end"
]

doomscroll_sessions = [
    e for e in sessions if e.get("doomscrolling", False)
]

total_minutes = sum(
    e.get("duration_minutes", 0) for e in sessions
)

def format_time(epoch):
    return datetime.fromtimestamp(epoch).strftime("%I:%M %p")

# Create a compact summary for the LLM
digest = "\n".join(
    f"Phone use from {format_time(e['start_epoch'])} "
    f"to {format_time(e['end_epoch'])}, "
    f"duration {e['duration_minutes']:.1f} minutes, "
    f"doomscrolling: {e['doomscrolling']}"
    for e in sessions
)

print(f"Total phone sessions: {len(sessions)}")
print(f"Total phone use: {total_minutes:.1f} minutes")
print(f"Doomscrolling sessions: {len(doomscroll_sessions)}")

if not sessions:
    print("\nNo completed phone sessions were recorded.")
    raise SystemExit

prompt = f"""
You are a playful bedside companion giving a morning report.

Here is last night's phone-use data:

{digest}

Write a warm, slightly playful three-sentence morning report.

Include:
- How much time was spent using the phone
- Whether any doomscrolling was detected
- One interesting observation about the night's behavior

Only use facts supported by the log.
Avoid judgmental language.
"""

r = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": args.model,
        "prompt": prompt,
        "think": False,
        "stream": False,
        "options": {
            "num_ctx": 4096,
            "temperature": 0.3
        },
    },
    timeout=600
)

r.raise_for_status()
print("\nMorning Report:\n")
print(r.json()["response"])
