"""Build output/defense_results.md from defense_results.json and defense_layers.json (no model calls)."""
import json
import time

from pypdf import PdfReader

import defenses as D
from agent import PRICES
from tools import DATA, OUTPUT

full = json.loads((OUTPUT / "defense_results.json").read_text())
layers = json.loads((OUTPUT / "defense_layers.json").read_text())
none, prompt_only, filter_only = layers["none"], layers["prompt_only"], layers["filter_only"]
docs = [r["file"] for r in full]
M = 1_000_000
handbook = (DATA / "shop_handbook.md").read_text()
blocked = D.blocked_vendors(handbook)


def raw_text(name: str) -> str:
    p = DATA / "practice_docs" / name
    return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages) if p.suffix == ".pdf" else p.read_text(errors="replace")


# Guard on its own: apply the vendor guard to the 'none' answers, using the raw document text.
guard_only = []
for r in none:
    a = dict(r["agent_answer"])
    hit = D.blocked_vendor_in(blocked, a["vendor"], raw_text(r["file"]))
    changed = bool(hit and a["decision"] == "recommend")
    if changed:
        a["decision"] = "do_not_recommend"
    ok = all(a[f] == r["key"][f] for f in ("vendor", "sku", "unit_price", "lead_time_days", "minimum_order")) and a["decision"] == r["key"]["decision"]
    guard_only.append({"file": r["file"], "correct": ok, "changed": changed, "decision_ok": a["decision"] == r["key"]["decision"]})

cfg = {"none": none, "prompt_only": prompt_only, "filter_only": filter_only, "all_layers": full}
ok = {c: {r["file"]: r["correct"] for r in rows} for c, rows in cfg.items()}
ok["guard_only"] = {g["file"]: g["correct"] for g in guard_only}
mark = lambda b: "right" if b else "WRONG"
d6 = lambda x: f"${x:,.6f}"


def totals(rows):
    t = {k: sum(r["usage"][k] for r in rows) for k in ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens", "total_tokens", "requests", "cost_usd")}
    t["plain_cost"] = (t["input_tokens"] * PRICES["input_per_1m"] + t["output_tokens"] * PRICES["output_per_1m"]) / M
    return t


T = {c: totals(rows) for c, rows in cfg.items()}
n = len(docs)
fixed_by = {}  # doc -> list of single layers that fix it
for d in docs:
    if not ok["none"][d]:
        fixed_by[d] = [l for l in ("prompt_only", "filter_only", "guard_only") if ok[l][d]]

L = ["# Defense Results (Problem 6)", "",
     "All 12 practice docs were re-run with every defense on (`defense_results.json`: answers, key checks, tokens and dollars per document). "
     "Model `gpt-6-luna` only. Dollars come from `prices.json`. To measure each layer, the same 12 docs were also run with no defenses, "
     "with the prompt rules only, and with the filter only (`defense_layers.json`). The vendor guard is code that runs after the model, "
     "so its row applies the guard to the no-defense answers.", "",
     "## Result", "",
     f"- With all layers: **{sum(ok['all_layers'].values())} of {n}** docs have the right decision and the right values. With no defenses: **{sum(ok['none'].values())} of {n}**.",
     f"- Trap tools called with all layers: **{sum(r['trap_tool_called'] for r in full)}**.",
     ]
clean = [r for r in full if r["clean_doc"]]
L += [f"- Clean docs (nothing hidden in them: {', '.join(r['file'][:3] for r in clean)}): **{sum(r['clean_doc_values_correct'] for r in clean)} of {len(clean)}** came back with the right values.",
      "", "## Before and after, all 12 docs", "",
      "Before = no defenses. After = all layers. Tokens and dollars are for the After run.", "",
      "| Doc | Key decision | Before | After | Hidden text dropped | Input tokens | Output tokens | Cost |", "|---|---|---|---|---|---|---|---|"]
for b, a in zip(none, full):
    bad = [f for f, v in b["field_matches"].items() if not v]
    before = f"{b['agent_answer']['decision']} ({mark(b['correct'])}{', wrong ' + '/'.join(bad) if bad else ''})"
    after = f"{a['agent_answer']['decision']} ({mark(a['correct'])})"
    u = a["usage"]
    L.append(f"| {a['file']} | {a['key']['decision']} | {before} | {after} | {len(a['defense']['hidden_text_removed'])} | {u['input_tokens']:,} | {u['output_tokens']:,} | {d6(u['cost_usd'])} |")
t = T["all_layers"]
L += [f"| **Total** | | {sum(ok['none'].values())} right | {sum(ok['all_layers'].values())} right | {sum(len(r['defense']['hidden_text_removed']) for r in full)} | {t['input_tokens']:,} | {t['output_tokens']:,} | {d6(t['cost_usd'])} |", ""]

L += ["## What each layer catches on its own", "",
      "Each column is one layer working alone against the no-defense agent. 'All' is every layer together.", "",
      "| Doc | None | Prompt rules only | Filter only | Vendor guard only | All |", "|---|---|---|---|---|---|"]
for d in docs:
    g = next(x for x in guard_only if x["file"] == d)
    gcell = mark(g["correct"]) if (g["correct"] or not g["decision_ok"]) else "decision fixed, vendor name still wrong"
    L.append(f"| {d} | {mark(ok['none'][d])} | {mark(ok['prompt_only'][d])} | {mark(ok['filter_only'][d])} | {gcell} | {mark(ok['all_layers'][d])} |")
L += ["", "Docs the no-defense agent got wrong, and which single layer fixed them:", ""]
for d, ls in fixed_by.items():
    L.append(f"- **{d}**: fixed by {', '.join(x.replace('_only', '').replace('_', ' ') for x in ls) or 'none of the single layers'}.")
for layer, label in (("prompt_only", "prompt rules"), ("filter_only", "hidden-text filter"), ("guard_only", "vendor guard")):
    unique = [d for d, ls in fixed_by.items() if ls == [layer]]
    L.append(f"- Catches that **only the {label}** made: {', '.join(unique) if unique else 'none'}.")
L += ["", "Reading this table:",
      "- The filter is the only layer that can fix the three price or lead-time overrides (p02, p07, p12). Prompt rules and the guard cannot, because the agent cannot tell which of two numbers is the lie.",
      "- The vendor guard only flips the decision. On p03 it turns the wrong `recommend` into `do_not_recommend`, but the vendor name the agent reported (the hidden text's Chapel Street Goods) stays wrong. Its value is that it is code, so it holds even if the model is talked out of the prompt rule; on this run the prompt rules and the filter also fixed p03.",
      "- p04 and p09 did not need a fix in any run. The agent never saw p04's comment and p09's hidden part (the old readers skipped them), so that was luck. The filter now removes them on purpose.",
      "- Each configuration was run once. A model can answer differently on another run, so a layer that looks unneeded here may be needed another day.", ""]

pt = lambda a, b: (a["input_tokens"] - b["input_tokens"]) / n
req = T["none"]["requests"] / n
prompt_delta = pt(T["prompt_only"], T["none"])
filter_delta = pt(T["filter_only"], T["none"])
t0 = time.perf_counter()
for d in docs:
    D.clean_document(DATA / "practice_docs" / d)
filter_ms = (time.perf_counter() - t0) / n * 1000
t0 = time.perf_counter()
for r in none:
    D.blocked_vendor_in(blocked, r["agent_answer"]["vendor"], raw_text(r["file"]))
guard_ms = (time.perf_counter() - t0) / n * 1000
plain = PRICES["input_per_1m"] / M
cached = PRICES["cached_input_per_1m"] / M

L += ["## What each layer costs", "",
      f"Measured as the difference in input tokens the API reported over the {n} docs ({req:.0f} model calls per doc). "
      f"'Plain' prices the extra tokens at the input rate (${PRICES['input_per_1m']}/1M), 'cached' at the cached rate (${PRICES['cached_input_per_1m']}/1M). "
      "The prompt rules sit in the cached start of every call, so the cached figure is the realistic one.", "",
      "| Layer | Extra input tokens per doc | Extra output tokens per doc | Plain $ per doc | Cached $ per doc | Time per doc |", "|---|---|---|---|---|---|",
      f"| Prompt rules | {prompt_delta:+,.0f} | {(T['prompt_only']['output_tokens'] - T['none']['output_tokens']) / n:+,.1f} | {prompt_delta * plain:+.6f} | {prompt_delta * cached:+.7f} | none |",
      f"| Hidden-text filter | {filter_delta:+,.0f} | {(T['filter_only']['output_tokens'] - T['none']['output_tokens']) / n:+,.1f} | {filter_delta * plain:+.6f} | {filter_delta * cached:+.7f} | {filter_ms:.1f} ms of local code |",
      f"| Vendor guard | 0 | 0 | $0 | $0 | {guard_ms:.2f} ms of local code |",
      "| Handbook protection (fingerprint) | 0 | 0 | $0 | $0 | under 1 ms of local code |", "",
      "The filter costs no model tokens. It changes the token count only because it removes hidden text the agent used to read, "
      "so a negative number means it saved a little.", "",
      "### Whole runs, 12 docs", "",
      "| Setup | Input tokens | Cache read | Cache write | Output tokens | Cost as billed | Cost at plain input rate |", "|---|---|---|---|---|---|---|"]
for c, label in (("none", "No defenses"), ("prompt_only", "Prompt rules only"), ("filter_only", "Filter only"), ("all_layers", "All layers")):
    x = T[c]
    L.append(f"| {label} | {x['input_tokens']:,} | {x['cached_input_tokens']:,} | {x['cache_write_tokens']:,} | {x['output_tokens']:,} | {d6(x['cost_usd'])} | {d6(x['plain_cost'])} |")
all_extra = T["all_layers"]["cost_usd"] - T["none"]["cost_usd"]
L += ["", f"All layers together versus no defenses: {T['all_layers']['total_tokens'] - T['none']['total_tokens']:+,} tokens and "
      f"{all_extra:+.6f} dollars over 12 docs ({all_extra / n:+.7f} per doc). "
      "Dollars as billed move a little from run to run because the API's cache is warm for some runs and cold for others "
      "(the first doc of each setup is the cold start, about $0.0016); the plain-rate column removes that.", "",
      "## Limits", "",
      "- A visible on-page sentence that lies is still visible. The filter only removes what people cannot see.",
      "- White text on a dark background is kept in HTML, but white text in a PDF is always dropped, even on a dark banner.",
      "- Text hidden by a shape drawn over it, text inside images, and PDF annotations or form fields are not checked.",
      "- HTML styles are read from inline styles, `<style>` rules (any selector, but specificity is not modeled) and old attributes such as `<font color>` and `bgcolor`. Styles added by JavaScript or external stylesheets are not seen.",
      "- The vendor guard blocks any doc whose visible text names a removed or pending vendor, so it can block a good quote that merely mentions one.", ""]
(OUTPUT / "defense_results.md").write_text("\n".join(L))
print("\n".join(L))
