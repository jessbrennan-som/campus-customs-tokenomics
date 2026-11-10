"""Problem 4: run the vendor desk agent on all 12 practice docs with and without prompt caching.

  no_cache : a random ID at the top of the prompt on every model call, so nothing can be reused.
  cache    : the normal agent; the handbook prefix is identical on every call.
Run:  .venv/bin/python cache_test.py
Every model call (not just every run) is saved to output/cache_test.json.
"""
import json
from dataclasses import asdict
from datetime import datetime

from pydantic_ai.messages import ModelResponse

from agent import MODEL_NAME, PRICES, build_agent, cost_usd
from tools import BASE, DATA, OUTPUT, Deps

DOCS = sorted(p for p in (DATA / "practice_docs").iterdir() if p.is_file() and not p.name.startswith("."))
calls = []

for setup in ["no_cache", "cache"]:
    agent = build_agent(no_cache=(setup == "no_cache"))
    for doc in DOCS:
        rel = str(doc.relative_to(BASE))
        result = agent.run_sync(f"Process this vendor document: {rel}", deps=Deps())
        n = 0
        for msg in result.all_messages():
            if isinstance(msg, ModelResponse):
                n += 1
                u = msg.usage
                calls.append({
                    "setup": setup,
                    "doc": doc.name,
                    "call_number_in_run": n,
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "model": MODEL_NAME,
                    "usage_reported_by_api": asdict(u),
                    "cost_usd": cost_usd(u)["total"],
                })
        print(setup, doc.name, "->", result.output.decision, flush=True)

OUTPUT.mkdir(exist_ok=True)
(OUTPUT / "cache_test.json").write_text(json.dumps(calls, indent=2))
print(f"saved {len(calls)} model calls")
