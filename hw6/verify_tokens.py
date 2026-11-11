"""Verify the handbook token count with real gpt-6-luna calls through Portkey.

Makes two tiny calls and compares usage.prompt_tokens:
  1. system = handbook, user = "Reply with OK."
  2. user = "Reply with OK." only (baseline)
The difference is the handbook's token cost on the API (including a few
tokens of message wrapper). Cost is roughly $0.001 for both calls.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parents[1] / ".env")  # Lecture 2/.env

api_key = os.environ.get("PORTKEY_API_KEY")
if not api_key:
    raise SystemExit("PORTKEY_API_KEY is not set (add it to .env).")

MODEL = os.environ.get("OPENAI_MODEL", "gpt-6-luna")
client = OpenAI(
    api_key=api_key,
    base_url="https://api.portkey.ai/v1",
    default_headers={"x-portkey-api-key": api_key, "x-portkey-provider": "openai"},
)

handbook = (HERE / "data" / "shop_handbook.md").read_text(encoding="utf-8")
question = {"role": "user", "content": "Reply with OK."}


def prompt_tokens(messages):
    r = client.chat.completions.create(
        model=MODEL, messages=messages, max_completion_tokens=200
    )
    details = getattr(r.usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) if details else 0
    return r.model, r.usage.prompt_tokens, cached


model, with_hb, cached = prompt_tokens([{"role": "system", "content": handbook}, question])
_, baseline, _ = prompt_tokens([question])

print(f"Model reported by API:        {model}")
print(f"Prompt tokens with handbook:  {with_hb} (cached: {cached})")
print(f"Prompt tokens baseline:       {baseline}")
print(f"Handbook tokens (difference): {with_hb - baseline}")
print("tiktoken o200k_base estimate: 10058")
