"""Turn output/cache_test.json into output/cache_test.md (no model calls)."""
import json
from collections import defaultdict

from agent import PRICES
from tools import OUTPUT

calls = json.loads((OUTPUT / "cache_test.json").read_text())
M = 1_000_000
P2_TOKENS = 10_058  # handbook tokens from output/handbook_estimate.md (Problem 2)
P2_INPUT, P2_CACHED = P2_TOKENS * PRICES["input_per_1m"] / M, P2_TOKENS * PRICES["cached_input_per_1m"] / M


def plain_cost(u):
    """Same call if every input token were billed at the plain input rate (no cache-write premium)."""
    return (u["input_tokens"] * PRICES["input_per_1m"] + u["output_tokens"] * PRICES["output_per_1m"]) / M


docs = sorted({c["doc"] for c in calls})
per = defaultdict(lambda: defaultdict(float))  # per[setup][doc]
tok = defaultdict(lambda: defaultdict(int))
plain = defaultdict(float)
n_calls = defaultdict(int)
for c in calls:
    s, u = c["setup"], c["usage_reported_by_api"]
    per[s][c["doc"]] += c["cost_usd"]
    n_calls[s] += 1
    plain[s] += plain_cost(u)
    for k in ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens"):
        tok[s][k] += u[k]

tot = {s: sum(per[s].values()) for s in per}
avg = {s: tot[s] / len(docs) for s in per}
saved = (tot["no_cache"] - tot["cache"]) / tot["no_cache"] * 100
saved_plain = (plain["no_cache"] - tot["cache"]) / plain["no_cache"] * 100
calls_per_doc = n_calls["cache"] / len(docs)
p2_doc_nc, p2_doc_c = P2_INPUT * calls_per_doc, P2_CACHED * calls_per_doc
warm = [c for c in calls if c["setup"] == "cache" and c["doc"] != docs[0]]
warm_avg = sum(c["cost_usd"] for c in warm) / (len(docs) - 1)


def d(x, n=6):
    return f"${x:,.{n}f}"


L = ["# Cache Test (Problem 4)", "",
     "Model `gpt-6-luna` only. Same agent, same 12 practice docs, two setups. Every model call is in `cache_test.json` "
     f"({len(calls)} calls: {calls_per_doc:.0f} per doc per setup). Dollars come from `prices.json`.", "",
     "- **no_cache**: a random ID goes at the very top of the prompt on every model call, so nothing can be reused.",
     "- **cache**: the normal agent, with the same handbook prefix on every call.", "",
     "## Tokens reported by the API (all 12 docs)", "",
     "| Setup | Input | Cache read | Cache write | Output |", "|---|---|---|---|---|"]
for s in ("no_cache", "cache"):
    t = tok[s]
    L.append(f"| {s} | {t['input_tokens']:,} | {t['cache_read_tokens']:,} | {t['cache_write_tokens']:,} | {t['output_tokens']:,} |")
L += ["", "Input includes the cache read and cache write tokens.", "",
      "## Cost", "", "| Setup | Total (12 docs) | Per document |", "|---|---|---|"]
for s in ("no_cache", "cache"):
    L.append(f"| {s} | {d(tot[s])} | {d(avg[s])} |")
L += ["", f"**Saved with caching: {saved:.1f}%**", "",
      "### Cost per document", "", "| Document | no_cache | cache |", "|---|---|---|"]
for doc in docs:
    L.append(f"| {doc} | {d(per['no_cache'][doc])} | {d(per['cache'][doc])} |")
L += ["", "Note: the API still reported cache-write tokens on the no_cache calls (the unique prefix is written to the cache "
      "but never read), and `prices.json` charges cache writes at $0.125 per 1M, more than plain input at $0.10. "
      f"If those tokens were billed as plain input instead, no_cache would total {d(plain['no_cache'])} and caching would save "
      f"{saved_plain:.1f}%.", "",
      "## Compared with the Problem 2 table", "",
      f"Problem 2 priced the handbook alone ({P2_TOKENS:,} tokens): {d(P2_INPUT)} per call at the input rate, "
      f"{d(P2_CACHED)} per call at the cached rate. With {calls_per_doc:.0f} calls per doc:", "",
      "| | Problem 2 estimate (handbook only) | Measured here | Measured / estimate |", "|---|---|---|---|",
      f"| Per doc, no cache | {d(p2_doc_nc)} | {d(avg['no_cache'])} | {avg['no_cache']/p2_doc_nc:.2f}x |",
      f"| Per doc, cache | {d(p2_doc_c)} | {d(avg['cache'])} | {avg['cache']/p2_doc_c:.2f}x |",
      f"| Saving from caching | {(1-p2_doc_c/p2_doc_nc)*100:.1f}% | {saved:.1f}% | |", "",
      "The measured numbers are higher because each call also carries `prompt.md`, the tool definitions and the "
      "document text, the model writes an answer (output costs $0.50 per 1M), no_cache calls pay the cache-write "
      f"rate, and the first cache call ({docs[0]}) was a cold start that wrote the whole prompt. "
      f"Per doc, cache after the cold start: {d(warm_avg)}.", "",
      "## Projection: 1,000 docs a day for 3 days (3,000 docs)", "",
      "| Basis | Per day (1,000 docs) | 3 days (3,000 docs) |", "|---|---|---|"]
for label, per_doc in [
    ("Measured, no cache", avg["no_cache"]),
    ("Measured, cache", avg["cache"]),
    ("Measured, cache (warm, after cold start)", warm_avg),
    ("Problem 2 estimate, no cache", p2_doc_nc),
    ("Problem 2 estimate, cache", p2_doc_c),
]:
    L.append(f"| {label} | {d(per_doc*1000, 2)} | {d(per_doc*3000, 2)} |")
L += ["", f"Measured saving over 3 days: {d((avg['no_cache']-avg['cache'])*3000, 2)} ({saved:.1f}%).",
      "Projection assumes the average of these 12 docs holds, and that the cache stays warm (calls come "
      "close together; the API drops cached prompts after a short idle time)."]
(OUTPUT / "cache_test.md").write_text("\n".join(L) + "\n")
print("\n".join(L))
