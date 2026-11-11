"""Campus Customs Vendor Desk agent - DEFENDED (Problem 6). gpt-6-luna via Portkey.

Three defense layers (details in defenses.py and output/harness.md, Safety section):
  1. Code    - the document is sanitized and scanned before the model sees it.
  2. Design  - code passes in the one assigned document (no file-reading tool), code makes the final
               purchasing decision, and send_email / approve_payment sit behind a human-approval gate.
  3. Prompt  - prompts/prompt.md treats everything inside the document markers as untrusted data.

The undefended baseline is still agent.py (prompts/prompt_original_p3.md + tools.py).

Usage:
    python secure_agent.py p01 p08
Appends to output/usage_log.json and output/audit_trail.json (cache_mode "defended"), and any action
attempts to output/trap_calls.json.
"""

from __future__ import annotations

import json
import sys
import uuid

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

import agent as va          # shared model client, cost and tool-activity helpers (not its prompt or tools)
import defenses
import tools
from models import DefendedDecision, VendorExtraction

DEFENDED_PROMPT = va.ROOT / "prompts" / "prompt.md"
INSTRUCTIONS = (DEFENDED_PROMPT.read_text(encoding="utf-8")
                + "\n\n---\n\n# Reference: Campus Customs Shop Handbook\n\n" + va.HANDBOOK)


def build_secure_agent(force_fresh: bool = False) -> Agent[None, VendorExtraction]:
    base = va.build_agent()                 # reuse the Portkey + gpt-6-luna model setup
    settings = {}
    if force_fresh:                         # bypass Portkey's response cache in tests
        settings["extra_headers"] = {"x-portkey-cache-force-refresh": "true"}
    return Agent(
        base.model,
        output_type=VendorExtraction,
        instructions=INSTRUCTIONS,
        tools=[defenses.send_email, defenses.approve_payment],   # gated; no file access tool
        retries=1,
        model_settings=settings,
        name="vendor_desk[defended]",
    )


def run_secure_document(agent: Agent, name: str):
    """Returns (DefendedDecision | None, run record dict)."""
    run_id = uuid.uuid4().hex[:12]
    doc = defenses.sanitize_document(name)                  # layer 1: before the AI reads anything
    defenses.RUN_STATE.update(run_id=run_id, document=doc.name, blocked_actions=[])
    tools.CURRENT_RUN.update(run_id=run_id, document=doc.name)
    audit = {"timestamp": tools.now(), "run_id": run_id, "document": doc.name, "model": va.MODEL_NAME,
             "cache_mode": "defended", "sanitizer": doc.summary()}
    try:
        result = agent.run_sync(defenses.wrap_for_model(doc),
                                usage_limits=UsageLimits(request_limit=4, tool_calls_limit=2))
    except Exception as exc:
        audit.update(status="error", error=f"{type(exc).__name__}: {exc}")
        tools.append_json(va.AUDIT_LOG, audit)
        print(f"[{doc.name}] ERROR: {audit['error']}")
        return None, audit

    extraction: VendorExtraction = result.output
    decision = defenses.evaluate(extraction, doc, list(defenses.RUN_STATE["blocked_actions"]))  # layer 2
    usage = result.usage
    usage_rec = {
        "timestamp": tools.now(), "run_id": run_id, "document": doc.name, "model": va.MODEL_NAME,
        "cache_mode": "defended", "requests": usage.requests, "input_tokens": usage.input_tokens,
        "cache_read_tokens": usage.cache_read_tokens, "cache_write_tokens": usage.cache_write_tokens,
        "output_tokens": usage.output_tokens, "reasoning_tokens": usage.output_reasoning_tokens,
        "cost_usd": va.cost_usd(usage),
    }
    tools.append_json(va.USAGE_LOG, usage_rec)
    audit.update(
        status="ok",
        tool_calls=va.tool_activity(result.all_messages()),
        blocked_actions=list(defenses.RUN_STATE["blocked_actions"]),
        model_output=extraction.model_dump(),
        final_result=decision.model_dump(),
    )
    tools.append_json(va.AUDIT_LOG, audit)
    return decision, {**audit, "usage": usage_rec}


def main(names: list[str]) -> None:
    if not names:
        raise SystemExit(__doc__)
    va.ensure_trap_log()
    agent = build_secure_agent()
    for name in names:
        decision, _ = run_secure_document(agent, name)
        if decision:
            print(json.dumps(decision.model_dump(), indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
