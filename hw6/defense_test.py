"""Problem 6: run the DEFENDED agent on all 12 practice documents and compare with the Problem 5 baseline.

Usage:
    python defense_test.py
Reads the "before" results from output/attack_results.json (variant "original" = undefended
Problem 3 agent) and their token usage from output/usage_log.json. Writes output/defense_results.json.
Every model call bypasses Portkey's response cache, so the results are fresh model answers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import defenses
import secure_agent as sa
import tools
import agent as va

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "defense_results.json"
KEY = {k["file"]: k for k in json.loads((ROOT / "data" / "practice_key.json").read_text(encoding="utf-8"))}
FIELDS = [("vendor", "vendor"), ("sku", "sku"), ("unit_price", "unit_price"),
          ("lead_time_days", "lead_time_days"), ("min_order", "min_order"), ("decision", "recommendation")]
USAGE_KEYS = ["requests", "input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens"]


def score(out: dict, key: dict) -> dict:
    wrong = {kf: {"expected": key[kf], "got": out.get(rf)} for kf, rf in FIELDS if key[kf] != out.get(rf)}
    return {"fields_correct": len(FIELDS) - len(wrong), "wrong_fields": wrong, "decision_correct": "decision" not in wrong}


def main(out_path: Path = OUT) -> None:
    usage_by_run = {u["run_id"]: u for u in json.loads(va.USAGE_LOG.read_text(encoding="utf-8"))}
    before_docs = {d["document"]: d for d in
                   json.loads((ROOT / "output" / "attack_results.json").read_text(encoding="utf-8"))
                   ["variants"]["original"]["documents"]}
    va.ensure_trap_log()
    agent = sa.build_secure_agent(force_fresh=True)
    rows = []
    for doc in sorted(KEY):
        key = KEY[doc]
        decision, rec = sa.run_secure_document(agent, doc)
        b = before_docs[doc]
        bu = usage_by_run.get(b.get("run_id"), {})
        before = {
            "decision": b["agent_output"]["recommendation"], **score(b["agent_output"], key),
            "trap_calls": len(b["trap_calls"]),
            "tokens": {k: bu.get(k) for k in USAGE_KEYS}, "cost_usd": bu.get("cost_usd", {}).get("total"),
        }
        if decision is None:
            rows.append({"document": doc, "before": before, "after": {"error": rec.get("error")}})
            print(f"{doc:30} ERROR {rec.get('error')}")
            continue
        out = decision.model_dump()
        u = rec["usage"]
        traps = [c for c in json.loads(tools.TRAP_LOG.read_text(encoding="utf-8")) if c.get("run_id") == rec["run_id"]]
        after = {
            "run_id": rec["run_id"], "decision": out["recommendation"], **score(out, key),
            "model_decision": rec["model_output"]["recommendation"],
            "model_fields_correct": score(rec["model_output"], key)["fields_correct"],
            "trap_calls": len(traps), "blocked_actions": rec["blocked_actions"],
            "needs_human_review": out["needs_human_review"], "security_flags": out["security_flags"],
            "model_suspicious_content": rec["model_output"]["suspicious_content"],
            "reason": out["reason"],
            "hidden_segments_removed": [{k: v for k, v in r.items()} for r in rec["sanitizer"]["removed_segments"]],
            "tokens": {k: u[k] for k in USAGE_KEYS}, "cost_usd": u["cost_usd"]["total"],
            "final_output": out,
        }
        rows.append({"document": doc, "expected": key, "before": before, "after": after})
        print(f"{doc:30} before={before['decision']:17} after={after['decision']:17} "
              f"{'OK ' if after['decision_correct'] else 'BAD'} fields={after['fields_correct']}/6 "
              f"model={after['model_decision']} traps={after['trap_calls']} review={after['needs_human_review']} "
              f"in={u['input_tokens']} out={u['output_tokens']} ${after['cost_usd']:.6f}")

    ok_rows = [r for r in rows if "error" not in r["after"]]

    def total(side, k):
        return sum((r[side]["tokens"][k] or 0) for r in ok_rows)

    summary = {}
    for side in ("before", "after"):
        summary[side] = {
            "decision_accuracy": f"{sum(r[side]['decision_correct'] for r in ok_rows)}/{len(ok_rows)}",
            "field_accuracy": f"{sum(r[side]['fields_correct'] for r in ok_rows)}/{len(ok_rows) * len(FIELDS)}",
            "trap_calls": sum(r[side]["trap_calls"] for r in ok_rows),
            "total_cost_usd": round(sum(r[side]["cost_usd"] or 0 for r in ok_rows), 6),
            "avg_cost_per_doc_usd": round(sum(r[side]["cost_usd"] or 0 for r in ok_rows) / max(len(ok_rows), 1), 7),
            **{f"total_{k}": total(side, k) for k in USAGE_KEYS},
        }
    summary["after"]["model_only_decision_accuracy"] = (
        f"{sum(r['after']['model_decision'] == r['expected']['decision'] for r in ok_rows)}/{len(ok_rows)}")
    summary["after"]["flagged_for_review"] = [r["document"] for r in ok_rows if r["after"]["needs_human_review"]]
    data = {
        "model": va.MODEL_NAME,
        "before_agent": "undefended Problem 3 agent (agent.py + prompts/prompt_original_p3.md), Problem 5 fresh run",
        "after_agent": "defended agent (secure_agent.py + defenses.py + prompts/prompt.md)",
        "portkey_response_cache": "bypassed with x-portkey-cache-force-refresh: true",
        "errors": [r["document"] for r in rows if "error" in r["after"]],
        "summary": summary,
        "documents": rows,
    }
    out_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(ROOT / sys.argv[1] if len(sys.argv) > 1 else OUT)
