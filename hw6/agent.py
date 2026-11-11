"""Campus Customs Vendor Desk agent - UNDEFENDED baseline (PydanticAI + gpt-6-luna via Portkey).

This is the original Problem 3 agent, kept unchanged as the baseline for injection tests.
It uses prompts/prompt_original_p3.md and the raw tools in tools.py. The defended agent
(Problem 6) is secure_agent.py, which uses prompts/prompt.md and defenses.py.

Usage:
    python agent.py p01 p08            # by file prefix
    python agent.py p08_chapelst_email.eml

After each document it appends to:
    output/usage_log.json    token usage and cost
    output/audit_trail.json  tool activity and final result
    output/trap_calls.json   any send_email / approve_payment attempts (written by tools.py)
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

import tools
from models import VendorDecision

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
USAGE_LOG = OUTPUT / "usage_log.json"
AUDIT_LOG = OUTPUT / "audit_trail.json"
REQUIRED_MODEL = "gpt-6-luna"

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parents[1] / ".env")  # shared Lecture 2/.env

MODEL_NAME = os.environ.get("OPENAI_MODEL", REQUIRED_MODEL)
if not MODEL_NAME.startswith(REQUIRED_MODEL):
    raise SystemExit(f"HW6 must use {REQUIRED_MODEL}; OPENAI_MODEL is set to '{MODEL_NAME}'.")

PRICES = json.loads((ROOT / "data" / "prices.json").read_text(encoding="utf-8"))[REQUIRED_MODEL]
HANDBOOK = (ROOT / "data" / "shop_handbook.md").read_text(encoding="utf-8")
# Stable system prompt (instructions + full handbook) so repeated runs can hit the prompt cache.
INSTRUCTIONS = (
    (ROOT / "prompts" / "prompt_original_p3.md").read_text(encoding="utf-8")
    + "\n\n---\n\n# Reference: Campus Customs Shop Handbook\n\n"
    + HANDBOOK
)


# Prompt-cache setups (Problem 4). OpenAI caches an exact prompt prefix.
#   implicit: provider default - OpenAI picks cache breakpoints automatically (Problem 3 runs).
#   cache:    explicit mode + one breakpoint right after the instructions+handbook.
#   no_cache: explicit mode with no breakpoints, so nothing may be written or read.
CACHE_SETTINGS: dict[str, dict] = {
    "implicit": {},
    "cache": {"openai_prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
              "openai_cache_instructions": True},
    "no_cache": {"openai_prompt_cache_options": {"mode": "explicit"},
                 "openai_cache_instructions": False},
}


def build_agent(cache_mode: str = "implicit") -> Agent[None, VendorDecision]:
    if cache_mode not in CACHE_SETTINGS:
        raise ValueError(f"cache_mode must be one of {list(CACHE_SETTINGS)}")
    api_key = os.environ.get("PORTKEY_API_KEY")
    if not api_key:
        raise SystemExit("PORTKEY_API_KEY is not set (add it to .env).")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.portkey.ai/v1",
        default_headers={"x-portkey-api-key": api_key, "x-portkey-provider": "openai"},
        timeout=90,
        max_retries=1,
    )
    model = OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
    return Agent(
        model,
        output_type=VendorDecision,
        instructions=INSTRUCTIONS,
        tools=[tools.read_document, tools.send_email, tools.approve_payment],
        retries=1,
        model_settings=CACHE_SETTINGS[cache_mode],
        name=f"vendor_desk[{cache_mode}]",
    )


def cost_usd(usage) -> dict[str, float]:
    """Cost from prices.json. OpenAI counts cached tokens inside input_tokens."""
    # input_tokens includes both cache-read and cache-write tokens, so each input token
    # is priced exactly once: as uncached input, a cache read, or a cache write.
    per = 1_000_000
    read, write = usage.cache_read_tokens, usage.cache_write_tokens
    uncached = max(usage.input_tokens - read - write, 0)
    parts = {
        "uncached_input": uncached * PRICES["input_per_1m"] / per,
        "cached_input": read * PRICES["cached_input_per_1m"] / per,
        "cache_write": write * PRICES["cache_write_per_1m"] / per,
        "output": usage.output_tokens * PRICES["output_per_1m"] / per,
    }
    parts["total"] = sum(parts.values())
    return {k: round(v, 8) for k, v in parts.items()}


def tool_activity(messages) -> list[dict]:
    """Pair every tool call with its result from the run's message history."""
    calls: dict[str, dict] = {}
    for message in messages:
        for part in message.parts:
            if isinstance(message, ModelResponse) and isinstance(part, ToolCallPart):
                calls[part.tool_call_id] = {"tool": part.tool_name, "arguments": part.args_as_dict()}
            elif isinstance(message, ModelRequest) and isinstance(part, ToolReturnPart):
                entry = calls.setdefault(part.tool_call_id, {"tool": part.tool_name})
                content = str(part.content)
                entry["result_preview"] = content[:300] + ("..." if len(content) > 300 else "")
    return [c for c in calls.values() if c["tool"] != "final_result"]


def run_document(agent: Agent, name: str, cache_mode: str = "implicit"):
    """Run the agent on one document, append to the logs, and return the PydanticAI result (or None)."""
    run_id = uuid.uuid4().hex[:12]
    document = tools.resolve_document(name).name
    tools.CURRENT_RUN.update(run_id=run_id, document=document)
    traps_before = len(json.loads(tools.TRAP_LOG.read_text(encoding="utf-8"))) if tools.TRAP_LOG.exists() else 0

    audit = {"timestamp": tools.now(), "run_id": run_id, "document": document, "model": MODEL_NAME,
             "cache_mode": cache_mode}
    try:
        result = agent.run_sync(
            f"Evaluate the vendor document '{document}'.",
            usage_limits=UsageLimits(request_limit=6, tool_calls_limit=4),
        )
    except Exception as exc:  # log the failure, keep going with other documents
        audit.update(status="error", error=f"{type(exc).__name__}: {exc}")
        tools.append_json(AUDIT_LOG, audit)
        print(f"[{document}] ERROR: {audit['error']}")
        return None

    usage = result.usage
    traps_after = len(json.loads(tools.TRAP_LOG.read_text(encoding="utf-8"))) if tools.TRAP_LOG.exists() else 0
    decision: VendorDecision = result.output

    tools.append_json(USAGE_LOG, {
        "timestamp": tools.now(), "run_id": run_id, "document": document, "model": MODEL_NAME,
        "cache_mode": cache_mode, "requests": usage.requests, "input_tokens": usage.input_tokens,
        "cache_read_tokens": usage.cache_read_tokens, "cache_write_tokens": usage.cache_write_tokens,
        "output_tokens": usage.output_tokens, "reasoning_tokens": usage.output_reasoning_tokens,
        "cost_usd": cost_usd(usage),
    })
    audit.update(
        status="ok",
        tool_calls=tool_activity(result.all_messages()),
        trap_calls_this_run=traps_after - traps_before,
        final_result=decision.model_dump(),
    )
    tools.append_json(AUDIT_LOG, audit)
    return result


def ensure_trap_log() -> None:
    if not tools.TRAP_LOG.exists():  # empty list = no trap calls so far
        tools.TRAP_LOG.parent.mkdir(parents=True, exist_ok=True)
        tools.TRAP_LOG.write_text("[]", encoding="utf-8")


def main(names: list[str]) -> None:
    if not names:
        raise SystemExit(__doc__)
    agent = build_agent()
    ensure_trap_log()
    for name in names:
        result = run_document(agent, name)
        if result:
            print(json.dumps(result.output.model_dump(), indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
