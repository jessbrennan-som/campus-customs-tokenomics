"""Campus Customs vendor desk agent (PydanticAI, gpt-6-luna through Portkey).

Run:  .venv/bin/python agent.py --doc data/practice_docs/p01_bluehen_quote.html
"""
import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # hide the startup banner

from dotenv import find_dotenv, load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from defenses import blocked_vendor_in, blocked_vendors, check_handbook_unchanged, clean_document, handbook_fingerprint
from models import VendorDecision
from tools import ALL_TOOLS, BASE, DATA, OUTPUT, Deps, append_json, resolve_doc

MODEL_NAME = "gpt-6-luna"  # the ONLY model allowed in HW6
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
PRICES = json.loads((DATA / "prices.json").read_text())[MODEL_NAME]


def build_agent(no_cache: bool = False, prompt_rules: bool = True) -> Agent:
    """no_cache=True puts a fresh random ID at the very top of the instructions on EVERY model call,
    so the start of the prompt never matches an earlier call and the API cannot reuse it."""
    load_dotenv(find_dotenv(usecwd=True))
    key = os.environ.get("PORTKEY_API_KEY")
    if not key:
        sys.exit("PORTKEY_API_KEY is not set. Put it in the class .env file or export it in ~/.zshrc.")
    model = OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(base_url=PORTKEY_BASE_URL, api_key=key))
    prompt = (BASE / "prompts" / "prompt.md").read_text()
    if not prompt_rules:  # only used by defense_test.py to measure what the prompt rules add
        prompt = prompt.split("## Defense rules")[0].rstrip() + "\n"
    instructions = (
        prompt
        + "\n\n---\n\n"
        + (DATA / "shop_handbook.md").read_text()
    )
    if no_cache:
        text = instructions

        def instructions():  # called again before every model request
            return f"Request ID: {uuid.uuid4()}\n\n{text}"

    return Agent(model, output_type=VendorDecision, instructions=instructions, tools=ALL_TOOLS, deps_type=Deps)


def cost_usd(usage) -> dict:
    """Dollar cost from prices.json. input_tokens already includes cached tokens, so split them out."""
    cached = usage.cache_read_tokens
    written = usage.cache_write_tokens
    fresh = usage.input_tokens - cached - written
    total = (
        fresh * PRICES["input_per_1m"]
        + cached * PRICES["cached_input_per_1m"]
        + written * PRICES["cache_write_per_1m"]
        + usage.output_tokens * PRICES["output_per_1m"]
    ) / 1_000_000
    return {"total": round(total, 8)}


def run_document(agent: Agent, doc: Path, deps: Deps):
    """THE entry point for one document. Every run goes through these mandatory steps:
    1. hidden-text filter (what a person cannot see never reaches the agent; findings go to output/defense_log.json)
    2. the handbook is fingerprinted, and the run stops if it changed
    3. removed and pending vendors are blocked in code, whatever the model said
    Returns (answer, run result)."""
    handbook = DATA / "shop_handbook.md"
    fingerprint = handbook_fingerprint(handbook)
    clean = clean_document(doc)  # same filter the read tools use
    log = {"time": datetime.now().isoformat(timespec="seconds"), "doc": str(doc.relative_to(BASE)),
           "hidden_text_removed": clean.removed, "zero_width_characters_removed": clean.zero_width_removed}

    result = agent.run_sync(f"Process this vendor document: {doc.relative_to(BASE)}", deps=deps)
    check_handbook_unchanged(handbook, fingerprint)

    answer = result.output
    hit = blocked_vendor_in(blocked_vendors(handbook.read_text()), answer.vendor, clean.text)
    if hit and answer.decision == "recommend":
        name, status = hit
        log["vendor_guard"] = f"model said recommend for {answer.vendor}, but {name} is {status}; changed to do_not_recommend"
        why = "is on the removed vendor list" if status == "removed" else "is on the pending list and is not approved"
        answer = answer.model_copy(update={
            "decision": "do_not_recommend",
            "reason": f"The approved-vendor check fails because {name.title()} {why}.",
        })
    OUTPUT.mkdir(exist_ok=True)
    append_json(OUTPUT / "defense_log.json", log)
    return answer, result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True, help="path to one vendor document (.html, .pdf or .eml)")
    doc_arg = ap.parse_args().doc
    doc = resolve_doc(doc_arg)

    agent = build_agent()
    deps = Deps()
    started = datetime.now()
    t0 = time.perf_counter()
    answer, result = run_document(agent, doc, deps)
    seconds = time.perf_counter() - t0
    usage = result.usage

    OUTPUT.mkdir(exist_ok=True)
    append_json(OUTPUT / "usage_log.json", {
        "time": started.isoformat(timespec="seconds"),
        "doc": str(doc.relative_to(BASE)),
        "model": MODEL_NAME,
        "seconds": round(seconds, 2),
        "requests": usage.requests,
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.input_tokens + usage.output_tokens,
        "cost_usd": cost_usd(usage)["total"],
    })
    append_json(OUTPUT / "audit_trail.json", {
        "time": started.isoformat(timespec="seconds"),
        "doc": str(doc.relative_to(BASE)),
        "tool_calls": deps.audit,
        "final_answer": answer.model_dump(),
    })
    print(json.dumps(answer.model_dump(), indent=2))


if __name__ == "__main__":
    main()
