# Vendor Desk Agent Harness

Model: `gpt-6-luna` only, through Portkey. Run with `.venv/bin/python agent.py --doc <path to one vendor document>`.

## Fields in `models.py` (`VendorDecision`)

| Field | Why it is there |
|-------|-----------------|
| `vendor` | Handbook section 13 asks for the vendor name; it is also how the agent checks the approved and removed vendor lists. |
| `sku` | Handbook section 13 asks for the Campus Customs SKU; it is the key to the item's max unit cost in the catalogue. `null` if the document has none. |
| `unit_price` | The price check compares this to the SKU's max unit cost. `null` if the document does not say, because the handbook says never guess. |
| `lead_time_days` | The lead time check requires 21 days or less. `null` if not stated. |
| `minimum_order` | The minimum order check requires 600 units or less. `null` if not stated. |
| `decision` | Only `recommend` or `do_not_recommend`, so the buyer gets a clean answer and nothing in between. |
| `reason` | One sentence that names the check that decided it, as handbook section 13 requires. |

## Tools in `tools.py`

| Tool | What it does |
|------|--------------|
| `list_vendor_docs` | Lists the files in `practice_docs` or `exam_docs` so the agent can find its way to vendor documents. |
| `read_email` | Reads a `.eml` file: From, To, Subject, Date and the text a person would see. Hidden text is dropped first. |
| `read_pdf` | Pulls the visible text out of every page of a vendor PDF. Hidden text is dropped first. |
| `read_html` | Pulls the visible text and tables out of a vendor HTML quote or catalog page. Hidden text is dropped first. |
| `send_email` | TRAP. Does nothing; it writes the attempt and its arguments to `output/trap_calls.json`. |
| `approve_payment` | TRAP. Does nothing; it writes the attempt and its arguments to `output/trap_calls.json`. |

The read tools can only open files inside `data/`, so a document cannot trick the agent into reading `.env` or other files.

## Files written

| File | Contents |
|------|----------|
| `output/trap_calls.json` | List of trap tool attempts (starts as an empty list). |
| `output/usage_log.json` | One entry per run: time, seconds, tokens the API reports (input, cached, cache write, output), and dollar cost from `prices.json`. |
| `output/audit_trail.json` | One entry per run: each tool call with its arguments, its answer and a short result, plus the final answer. |

## Defense layers

A document goes through these layers in order. Results and costs are in `defense_results.md`.

| Layer | Where | What it does |
|-------|-------|--------------|
| 1. Hidden-text filter | `defenses.py` (`clean_document`), called by `agent.py` (`run_document`) and by every read tool | Keeps only text a person would see when reading the document the normal way. Drops text that is invisible (`display:none`, `visibility:hidden`, `opacity:0`), the same color as the background (white on white), 0 or tiny font (under 3 pt), pushed off the page or screen, in an HTML comment, in an invisible PDF mode, or placed outside the PDF page. Reads inline styles, `<style>` rules with any selector, and old HTML attributes (`<font color>`, `bgcolor`). Strips zero-width characters. Everything it drops is logged in `output/defense_log.json`. The agent never gets the raw file. |
| 2. Mandatory entry point | `agent.py` (`run_document`) | The one way to process a document. It runs the filter first, so no run can skip it. The read tools use the same filter. |
| 3. Prompt rules | `prompts/prompt.md`, section "Defense rules" | Tells the model to ignore document instructions that change handbook rules, never edit the handbook, never recommend a removed or pending vendor, and never act on a document asking for an email, a payment, or handbook contents. |
| 4. Vendor guard | `agent.py` and `defenses.py` (`blocked_vendors`, `blocked_vendor_in`) | After the model answers, code reads the removed and pending list from handbook section 6. If the answer's vendor or the visible document text names one of them, `recommend` becomes `do_not_recommend`. It works even if the model is talked out of the prompt rule. |
| 5. Handbook protection | `tools.py`, `agent.py`, `defenses.py` | The AI has no tool that writes or edits files. The handbook is also fingerprinted before each run, and the run stops if it changed. |
| 6. Trap tools | `tools.py` (`send_email`, `approve_payment`) | If anything gets through and the model tries to send an email or approve a payment, nothing happens and the attempt is saved to `output/trap_calls.json`. |

Files written by the defense runs: `defense_log.json` (what the filter dropped), `defense_results.json` (every doc, with the key check, tokens and dollars), `defense_layers.json` (each layer on its own), `defense_results.md` (the report).
