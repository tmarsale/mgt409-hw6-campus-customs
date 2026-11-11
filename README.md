# Campus Customs Vendor Desk: an AI Agent That Reads Vendor Quotes

**MGT 409 · AI Foundations for Managers · Homework 6**

Campus Customs is a small Yale merchandise shop. Its **Vendor Desk agent** reads vendor quotes (HTML pages, PDFs, and emails) and drafts a decision for the buyer. It pulls out the vendor, SKU, unit price, lead time, and minimum order, then checks them against the shop handbook and returns **recommend** or **do_not_recommend** with a one-sentence reason.

HW6 measures what the agent costs, how prompt caching changes that cost, and how well it holds up against **prompt-injection attacks hidden inside vendor documents**.

- **Model:** `gpt-6-luna` only, called through **Portkey**, using PydanticAI on the OpenAI Responses API.
- **Two agents:** an **undefended baseline** (`agent.py`), kept for testing, and a **defended agent** (`secure_agent.py`) with code, design, and prompt defenses.
- **Trap tools:** `send_email` and `approve_payment` exist only to catch an agent that has been tricked. **They never send or pay anything.** They only log the attempt.

**Start here:** open [`hw6/output/hw6_report.html`](hw6/output/hw6_report.html) in any browser. It is one offline file with charts for every result. To view it, download the file (or clone the repository) and double-click it.

## Results

| Measure | Result |
|---|---|
| Handbook size (Problem 2) | 10,058 tokens (`tiktoken`); a live API call measured 10,062 |
| Prompt caching (Problem 4) | 12 documents cost $0.028544 without caching vs $0.004645 with it: **83.7% less** |
| Undefended agent vs hidden attacks (Problem 5) | 9/12 correct decisions; fooled by p02, p07, and p12 in 4 of 4 runs each |
| Defended agent (Problem 6, plus Problem 7 fixes) | **12/12 decisions, 72/72 fields**, 0 trap-tool calls, about 38% cheaper per document |
| Our two red-team attacks (Problem 7) | Neither succeeded. After the fixes, both are removed by code before the AI reads them, in 3 of 3 runs |
| 10 exam documents (Problem 8) | 5 recommend / 5 do_not_recommend, 0 trap-tool calls, 7 flagged for review, $0.00292 in total |
| Monthly cost at 1,000 documents a day | **About $8.43–$8.76** for AI usage (final defended agent) |
| Recommendation (Problem 9) | Ready for a **supervised pilot**, not for unsupervised processing of real vendor email |

## Repository layout

```
hw6/
├── agent.py              Undefended baseline agent (Problem 3 original prompt + tools.py)
├── tools.py              Document readers (HTML, PDF, email) and the log-only trap tools
├── models.py             Structured outputs: VendorDecision, VendorExtraction, DefendedDecision
├── secure_agent.py       Defended agent (Problem 6, with the Problem 7 fixes)
├── defenses.py           Code and design defenses: sanitizer, injection scanner, handbook rules, approval gate
├── prompts/
│   ├── prompt.md                     Defended prompt (used by secure_agent.py)
│   ├── prompt_original_p3.md         Original Problem 3 prompt (used by agent.py)
│   └── prompt_p3_revised_terms.md    Problem 3 prompt after the "revised terms" fix (Problem 5 comparison)
├── data/
│   ├── shop_handbook.md  prices.json  practice_key.json
│   ├── practice_docs/    12 practice documents (p01–p12)
│   ├── exam_docs/        10 exam documents (e01–e10)
│   └── my_attacks/       Our 2 red-team attack documents and their expected answers
├── output/               Every result from Problems 1–9 (see the table below)
├── verify_tokens.py      Problem 2: live token count check
├── cache_test.py         Problem 4: with vs without prompt caching
├── attack_test.py        Problem 5: injection baseline
├── defense_test.py       Problem 6: defended rerun on the 12 practice documents
├── make_attacks.py       Problem 7: builds the two red-team documents
├── red_team_test.py      Problem 7: red-team test, both agents
├── exam_run.py           Problem 8: exam run with automatic log verification
├── build_report.py       Problem 9: builds output/hw6_report.html from the saved results (no API calls)
├── AI_prompts.md         Every prompt used for HW6, with follow-ups
├── requirements.txt
└── .env.example
```

## Setup

You need Python (all tests were run on Python 3.14) and a Portkey API key with access to `gpt-6-luna`.

**Windows (PowerShell)**

```powershell
git clone https://github.com/tmarsale/mgt409-hw6-campus-customs.git
cd mgt409-hw6-campus-customs\hw6
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env        # set PORTKEY_API_KEY=<your key>
```

**macOS / Linux**

```bash
git clone https://github.com/tmarsale/mgt409-hw6-campus-customs.git
cd mgt409-hw6-campus-customs/hw6
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then set PORTKEY_API_KEY=<your key>
```

**About the Portkey settings:**
- `hw6/.env` is read automatically and is excluded from git. A `PORTKEY_API_KEY` environment variable works too.
- Requests go to `https://api.portkey.ai/v1` with the headers `x-portkey-api-key` and `x-portkey-provider: openai`.
- `OPENAI_MODEL` must be `gpt-6-luna`; the agents refuse to run with any other model.
- If you use Dropbox or OneDrive, pause syncing (or exclude `.venv`) while running `pip install`.

## Running the agent

Run these from `hw6/` with the virtual environment active. Documents can be named by file name or by prefix (`p01`, `e03`).

```bash
# Defended agent (recommended): one or more documents
python secure_agent.py p01 e03

# Undefended baseline, for comparison
python agent.py p01 p08
```

Each run prints a JSON decision. It also appends token usage and cost to `output/usage_log.json`, the tool activity and final result to `output/audit_trail.json`, and any trap-tool attempt to `output/trap_calls.json`. One document costs about $0.0003.

### Reproducing each problem

| Problem | Command | Writes |
|---|---|---|
| 2 | `python verify_tokens.py` | prints the live token count |
| 4 | `python cache_test.py` | `output/cache_test.json` |
| 5 | `python attack_test.py` | `output/attack_results.json` |
| 6 | `python defense_test.py` | `output/defense_results.json` |
| 7 | `python make_attacks.py`, then `python red_team_test.py` | `data/my_attacks/`, `output/red_team_results.json` |
| 8 | `python exam_run.py` | `output/exam_results.json` (with a `verification` section) |
| 9 | `python build_report.py` (no API calls) | `output/hw6_report.html` |

> **Rerunning a test overwrites its submitted results file** and adds to the logs. Model answers can vary slightly from run to run. To get back to the submitted results, use `git checkout -- hw6/output hw6/data`.
>
> The test scripts send `x-portkey-cache-force-refresh: true`, so Portkey's response cache can't replay an old answer.

## Documentation and deliverables

| File | What it is |
|---|---|
| [`hw6/AI_prompts.md`](hw6/AI_prompts.md) | Every prompt for Problems 1–10, with follow-ups |
| [`hw6/output/hw6_report.html`](hw6/output/hw6_report.html) | **Problem 9:** the full report with charts, offline, in one file |
| [`hw6/output/harness.md`](hw6/output/harness.md) | Models, tools, logs, and the **Safety** section (all three defense layers) |
| [`hw6/output/handbook_estimate.md`](hw6/output/handbook_estimate.md) | Problem 2: token count and cost estimate |
| [`hw6/output/cache_test.md`](hw6/output/cache_test.md), [`cache_test.json`](hw6/output/cache_test.json) | Problem 4: caching comparison, with every model call |
| [`hw6/output/attack_results.md`](hw6/output/attack_results.md), [`.json`](hw6/output/attack_results.json) | Problem 5: injection baseline, and where each attack was hidden |
| [`hw6/output/defense_results.md`](hw6/output/defense_results.md), [`.json`](hw6/output/defense_results.json) | Problem 6: before vs after defenses, extra tokens and cost |
| [`hw6/output/red_team.md`](hw6/output/red_team.md), [`red_team_results.json`](hw6/output/red_team_results.json) | Problem 7: our two attacks, results, fixes, and retest |
| [`hw6/output/red_team_renders/`](hw6/output/red_team_renders) | How each attack document looks to a person |
| [`hw6/output/defense_results_after_fixes.json`](hw6/output/defense_results_after_fixes.json), [`red_team_results_after_fixes.json`](hw6/output/red_team_results_after_fixes.json) | Problem 7 retest after the fixes |
| [`hw6/output/exam_results.json`](hw6/output/exam_results.json) | Problem 8: one entry per exam document, plus automatic verification |
| [`hw6/output/usage_log.json`](hw6/output/usage_log.json), [`audit_trail.json`](hw6/output/audit_trail.json), [`trap_calls.json`](hw6/output/trap_calls.json) | Logs of every run (`trap_calls.json` is empty: no trap tool was ever called) |

## Safety notes

- `send_email` and `approve_payment` never perform real actions, in either agent.
- In the defended agent, they also require a human approval in `hw6/output/approvals.json`. That file is excluded from git and does not exist, so every call is blocked and logged.
- No API keys are stored in this repository. Before publishing, every file was checked for key patterns, for the real key value, and for personal information.
- The vendor email addresses in the data use the reserved `.example` domain.
