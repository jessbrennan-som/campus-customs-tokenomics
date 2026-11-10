# HW6: Campus Customs Vendor Desk Agent (MGT 409)

A PydanticAI agent that reads one vendor document (HTML quote, PDF quote or `.eml` email), checks it against the
shop handbook, and returns the vendor, SKU, unit price, lead time in days, minimum order, and a
`recommend` / `do_not_recommend` decision with a one-sentence reason.
It uses **only `gpt-6-luna`**, through Portkey. It has two trap tools (`send_email`, `approve_payment`) that do nothing
except log the attempt, and defenses against hidden text in documents.

## Run it

You need Python 3.10 or newer.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then open .env and paste your Portkey key
```

Run the agent on one document:

```bash
.venv/bin/python agent.py --doc data/practice_docs/p01_bluehen_quote.html
```

Other documents to try: `data/practice_docs/p08_chapelst_email.eml`, `data/exam_docs/e04_catalog.html`,
`data/my_attacks/a2_bluehen_weekly_reorder.eml`.

Each run appends to `output/usage_log.json` (tokens and dollars), `output/audit_trail.json` (every tool call) and
`output/defense_log.json` (hidden text the filter dropped). Trap tool attempts go to `output/trap_calls.json`.

## What is where

| Path | What it is |
|---|---|
| `agent.py` | Entry point. Runs the hidden-text filter, the agent, the handbook check and the vendor guard |
| `tools.py` | The agent's tools: read HTML, PDF and email, list documents, and the two trap tools |
| `models.py` | The answer format (`VendorDecision`) |
| `defenses.py` | Hidden-text filter, handbook lock and removed/pending vendor guard |
| `prompts/prompt.md` | The agent's instructions, including the defense rules (the handbook is added at run time) |
| `data/` | Handbook, prices, `practice_docs/`, `exam_docs/`, the answer key for practice, and `my_attacks/` (my two red-team documents) |
| `output/` | All results; start with `hw6_report.html` (double-click to open, no internet needed) and `harness.md` |
| `AI_prompts.md` | My prompt log for each problem |

## Scripts for each problem

| Script | Problem | Writes |
|---|---|---|
| `cache_test.py`, `cache_report.py` | 4: with and without cache | `output/cache_test.json`, `.md` |
| `attack_results.py` | 5: attack the agent | `output/attack_results.json` |
| `defense_test.py`, `defense_report.py` | 6: defenses and each layer | `output/defense_results.json`, `defense_layers.json`, `.md` |
| `red_team.py` | 7: red team | `output/red_team/` |
| `exam_run.py` | 8: exam documents | `output/exam_results.json` |
| `build_report.py` | 9: results page | `output/hw6_report.html` |

These scripts call the model and cost a few cents each. Logs from earlier runs mention the old folder name `data-4`; it is the same folder as `data/`.

No keys are stored in this repo: `.env` is ignored, and `.env.example` has a placeholder.
