"""Problem 8: run the final defended Vendor Desk agent on all exam documents.

Agent: secure_agent.py + defenses.py + prompts/prompt.md (Problem 6 defenses with the Problem 7 fixes).
Model: gpt-6-luna through Portkey; the Portkey response cache is bypassed so every answer is fresh.
Results are written exactly as the agent returns them - no manual edits.

Usage:
    python exam_run.py
Writes output/exam_results.json: one entry per document, plus an automatic verification section that
cross-checks the entries against output/usage_log.json, output/audit_trail.json, output/trap_calls.json,
and data/prices.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import agent as va
import defenses
import secure_agent as sa
import tools

ROOT = Path(__file__).resolve().parent
EXAM_DIR = ROOT / "data" / "exam_docs"
OUT = ROOT / "output" / "exam_results.json"
MAX_ATTEMPTS = 2   # retry only if the API call itself fails (e.g. timeout); never to change an answer
REQUIRED = ["file", "vendor", "sku", "unit_price", "lead_time_days", "min_order", "decision", "reason",
            "trap_tool_called", "input_tokens", "cached_tokens", "output_tokens", "cost_usd"]


def load(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def price_check(u: dict) -> float:
    """Independent cost recomputation from data/prices.json (each input token priced once)."""
    p = json.loads((ROOT / "data" / "prices.json").read_text(encoding="utf-8"))["gpt-6-luna"]
    uncached = u["input_tokens"] - u["cache_read_tokens"] - u["cache_write_tokens"]
    return (uncached * p["input_per_1m"] + u["cache_read_tokens"] * p["cached_input_per_1m"]
            + u["cache_write_tokens"] * p["cache_write_per_1m"] + u["output_tokens"] * p["output_per_1m"]) / 1e6


def run_all() -> tuple[list[dict], list[dict]]:
    if defenses.APPROVALS_FILE.exists():
        raise SystemExit("output/approvals.json exists - remove it so no action can be authorized.")
    va.ensure_trap_log()
    docs = sorted(p.name for p in EXAM_DIR.iterdir() if p.suffix.lower() in defenses.SANITIZERS)
    agent = sa.build_secure_agent(force_fresh=True)
    entries, failed_attempts = [], []
    for doc in docs:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            decision, rec = sa.run_secure_document(agent, doc)
            if decision is not None:
                break
            failed_attempts.append({"file": doc, "attempt": attempt, "run_id": rec["run_id"], "error": rec.get("error")})
        if decision is None:
            entries.append({"file": doc, "error": "agent failed after retries", "run_id": rec["run_id"]})
            print(f"{doc:28} FAILED")
            continue
        out = decision.model_dump()
        u = rec["usage"]
        traps = [t for t in load(tools.TRAP_LOG) if t.get("run_id") == rec["run_id"]]
        entries.append({
            "file": doc,
            "vendor": out["vendor"], "sku": out["sku"], "unit_price": out["unit_price"],
            "lead_time_days": out["lead_time_days"], "min_order": out["min_order"],
            "decision": out["recommendation"], "reason": out["reason"],
            "trap_tool_called": bool(traps),
            "trap_calls": [{"tool": t["tool"], "action_taken": t["action_taken"]} for t in traps],
            "input_tokens": u["input_tokens"], "cached_tokens": u["cache_read_tokens"],
            "cache_write_tokens": u["cache_write_tokens"], "output_tokens": u["output_tokens"],
            "reasoning_tokens": u["reasoning_tokens"], "cost_usd": u["cost_usd"]["total"],
            "needs_human_review": out["needs_human_review"], "security_flags": out["security_flags"],
            "model_decision": rec["model_output"]["recommendation"],
            "run_id": rec["run_id"], "attempts": attempt,
        })
        print(f"{doc:28} {out['recommendation']:17} vendor={out['vendor']} sku={out['sku']} price={out['unit_price']} "
              f"lead={out['lead_time_days']} min={out['min_order']} traps={len(traps)} review={out['needs_human_review']} "
              f"${u['cost_usd']['total']:.6f}")
    return entries, failed_attempts


def verify(entries: list[dict]) -> dict:
    usage = {u["run_id"]: u for u in load(va.USAGE_LOG)}
    audit = {a["run_id"]: a for a in load(va.AUDIT_LOG)}
    trap_log = load(tools.TRAP_LOG)
    expected = sorted(p.name for p in EXAM_DIR.iterdir() if p.suffix.lower() in defenses.SANITIZERS)
    files = [e["file"] for e in entries]
    problems: list[str] = []

    if sorted(files) != expected:
        problems.append(f"documents processed {sorted(files)} != exam folder {expected}")
    if len(files) != len(set(files)):
        problems.append("duplicate entries")
    missing = {e["file"]: [k for k in REQUIRED if k not in e] for e in entries if any(k not in e for k in REQUIRED)}
    if missing:
        problems.append(f"missing required fields: {missing}")
    null_values = {e["file"]: [k for k in REQUIRED if k in e and e[k] is None] for e in entries}
    null_values = {k: v for k, v in null_values.items() if v}
    for e in entries:
        if "error" in e:
            continue
        if e["decision"] not in ("recommend", "do_not_recommend"):
            problems.append(f"{e['file']}: bad decision {e['decision']}")
        if not e["reason"].strip():
            problems.append(f"{e['file']}: empty reason")
        u, a = usage.get(e["run_id"]), audit.get(e["run_id"])
        if not u or not a:
            problems.append(f"{e['file']}: run {e['run_id']} missing from usage or audit log")
            continue
        if u["model"] != "gpt-6-luna" or a["model"] != "gpt-6-luna":
            problems.append(f"{e['file']}: model is {u['model']}")
        for mine, theirs in (("input_tokens", "input_tokens"), ("cached_tokens", "cache_read_tokens"),
                             ("output_tokens", "output_tokens")):
            if e[mine] != u[theirs]:
                problems.append(f"{e['file']}: {mine} {e[mine]} != usage log {u[theirs]}")
        if abs(e["cost_usd"] - price_check(u)) > 1e-8:
            problems.append(f"{e['file']}: cost {e['cost_usd']} != recomputed {price_check(u):.8f}")
        logged = [t["tool"] for t in trap_log if t.get("run_id") == e["run_id"]]
        audited = [t["tool"] for t in a.get("tool_calls", []) if t["tool"] in ("send_email", "approve_payment")]
        blocked = a.get("blocked_actions", [])
        if e["trap_tool_called"] != bool(logged) or sorted(logged) != sorted(audited) or sorted(logged) != sorted(blocked):
            problems.append(f"{e['file']}: trap mismatch entry={e['trap_tool_called']} log={logged} "
                            f"audit={audited} blocked={blocked}")
    exam_trap_entries = [t for t in trap_log if t.get("document") in expected]
    unmatched = [t for t in exam_trap_entries if t.get("run_id") not in {e.get("run_id") for e in entries}]
    return {
        "documents_in_folder": len(expected),
        "entries": len(entries),
        "all_documents_processed": sorted(files) == expected and not any("error" in e for e in entries),
        "all_required_fields_present": not missing,
        "fields_with_null_values": null_values,
        "trap_calls_in_log_for_exam_docs": len(exam_trap_entries),
        "trap_log_entries_not_matched_to_an_entry": len(unmatched),
        "tokens_and_costs_match_usage_log_and_prices_json": not any("tokens" in p or "cost" in p for p in problems),
        "trap_flags_match_trap_log_audit_and_blocked_actions": not any("trap mismatch" in p for p in problems),
        "model_is_gpt_6_luna": not any("model is" in p for p in problems),
        "problems": problems,
        "passed": not problems and not unmatched,
    }


def main() -> None:
    entries, failed_attempts = run_all()
    data = {
        "model": va.MODEL_NAME,
        "agent": "secure_agent.py + defenses.py + prompts/prompt.md (Problem 6 defenses with Problem 7 fixes)",
        "prices": "data/prices.json (gpt-6-luna): input $0.10, cached input $0.01, cache write $0.125, output $0.50 per 1M",
        "portkey_response_cache": "bypassed with x-portkey-cache-force-refresh: true",
        "results_edited_manually": False,
        "documents": entries,
        "totals": {
            "documents": len(entries),
            "recommend": sum(e.get("decision") == "recommend" for e in entries),
            "do_not_recommend": sum(e.get("decision") == "do_not_recommend" for e in entries),
            "trap_tool_called": sum(bool(e.get("trap_tool_called")) for e in entries),
            "needs_human_review": sum(bool(e.get("needs_human_review")) for e in entries),
            "input_tokens": sum(e.get("input_tokens", 0) for e in entries),
            "cached_tokens": sum(e.get("cached_tokens", 0) for e in entries),
            "output_tokens": sum(e.get("output_tokens", 0) for e in entries),
            "cost_usd": round(sum(e.get("cost_usd", 0) for e in entries), 8),
        },
        "failed_api_attempts_retried": failed_attempts,
    }
    data["verification"] = verify(entries)
    OUT.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"totals": data["totals"], "verification": data["verification"]}, indent=2))


if __name__ == "__main__":
    main()
