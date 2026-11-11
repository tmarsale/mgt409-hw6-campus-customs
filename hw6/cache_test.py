"""Problem 4: run the Vendor Desk agent with and without prompt caching and log every model call.

Usage:
    python cache_test.py                       # all 12 practice docs, no_cache pass then cache pass
    python cache_test.py p01 --out some.json   # subset / custom output file (used for a probe run)

Each model call (an agent run makes ~2: read the document, then answer) is saved with the
document, cache setup, token counts reported by the API, cache diagnostics, and cost from
data/prices.json. A no_cache call that reports any cached or cache-write tokens is flagged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic_ai.messages import ModelResponse

import agent as va
import tools

ROOT = Path(__file__).resolve().parent
PRACTICE = sorted(p.name for p in (ROOT / "data" / "practice_docs").iterdir())
MODES = ["no_cache", "cache"]


def call_records(result, document: str, mode: str, pass_no: int) -> list[dict]:
    records = []
    responses = [m for m in result.all_messages() if isinstance(m, ModelResponse)]
    for i, resp in enumerate(responses, start=1):
        u = resp.usage
        details = resp.provider_details or {}
        records.append({
            "cache_mode": mode,
            "pass": pass_no,
            "document": document,
            "call": i,
            "calls_in_run": len(responses),
            "timestamp": resp.timestamp.isoformat(timespec="seconds"),
            "model_reported": resp.model_name,
            "input_tokens": u.input_tokens,
            "cache_read_tokens": u.cache_read_tokens,
            "cache_write_tokens": u.cache_write_tokens,
            "uncached_input_tokens": max(u.input_tokens - u.cache_read_tokens - u.cache_write_tokens, 0),
            "output_tokens": u.output_tokens,
            "reasoning_tokens": u.output_reasoning_tokens,
            "cost_usd": va.cost_usd(u),
            "cache_diagnostics": details.get("prompt_cache_diagnostics"),
            "no_cache_violation": mode == "no_cache" and (u.cache_read_tokens > 0 or u.cache_write_tokens > 0),
            "decision": result.output.recommendation if i == len(responses) else None,
        })
    return records


def main(argv: list[str]) -> None:
    out = ROOT / "output" / "cache_test.json"
    if "--out" in argv:
        i = argv.index("--out")
        out = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    docs = [tools.resolve_document(a).name for a in argv] or PRACTICE

    va.ensure_trap_log()
    records: list[dict] = []
    for pass_no, mode in enumerate(MODES, start=1):
        agent = va.build_agent(cache_mode=mode)
        for doc in docs:
            result = va.run_document(agent, doc, cache_mode=mode)
            if result is None:
                records.append({"cache_mode": mode, "pass": pass_no, "document": doc, "error": True})
                continue
            recs = call_records(result, doc, mode, pass_no)
            records.extend(recs)
            r = recs[-1]
            print(f"{mode:9} {doc:30} calls={len(recs)} "
                  f"read={sum(x['cache_read_tokens'] for x in recs):6} "
                  f"write={sum(x['cache_write_tokens'] for x in recs):6} "
                  f"in={sum(x['input_tokens'] for x in recs):6} "
                  f"cost={sum(x['cost_usd']['total'] for x in recs):.6f} {r['decision']}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"model": va.MODEL_NAME, "prices": va.PRICES,
                                   "cache_settings": va.CACHE_SETTINGS, "calls": records},
                                  indent=2, default=str), encoding="utf-8")

    bad = [r for r in records if r.get("no_cache_violation")]
    print(f"\nSaved {len(records)} call records to {out}")
    print(f"no_cache calls with cached/cache-write tokens: {len(bad)}")


if __name__ == "__main__":
    main(sys.argv[1:])
