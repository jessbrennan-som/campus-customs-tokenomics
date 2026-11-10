"""Problem 8: run the final patched agent (all defenses on) on every doc in data/exam_docs.
Saves output/exam_results.json exactly as the agent produced it (nothing edited by hand). Model: gpt-6-luna only."""
import json

from agent import build_agent, cost_usd, run_document
from tools import DATA, OUTPUT, TRAP_FILE, Deps


def trap_count() -> int:
    return len(json.loads(TRAP_FILE.read_text())) if TRAP_FILE.exists() and TRAP_FILE.read_text().strip() else 0


docs = sorted(p for p in (DATA / "exam_docs").iterdir() if p.is_file() and not p.name.startswith("."))
agent = build_agent()
results = []
start_log = len(json.loads((OUTPUT / "defense_log.json").read_text()))
for doc in docs:
    before = trap_count()
    answer, result = run_document(agent, doc, Deps())
    u = result.usage
    results.append({
        "file": doc.name,
        "vendor": answer.vendor,
        "sku": answer.sku,
        "unit_price": answer.unit_price,
        "lead_time_days": answer.lead_time_days,
        "min_order": answer.minimum_order,
        "decision": answer.decision,
        "reason": answer.reason,
        "trap_tool_called": trap_count() > before,
        "input_tokens": u.input_tokens,
        "cached_tokens": u.cache_read_tokens,
        "output_tokens": u.output_tokens,
        "cost_usd": cost_usd(u)["total"],
    })
    print(f"{doc.name}: {answer.decision} trap={results[-1]['trap_tool_called']} ${results[-1]['cost_usd']:.6f}", flush=True)
(OUTPUT / "exam_results.json").write_text(json.dumps(results, indent=2))
print("saved output/exam_results.json")
