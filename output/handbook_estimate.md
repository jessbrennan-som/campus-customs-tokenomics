# Handbook Estimate

## Size of `data/shop_handbook.md`

| Measure | Count |
|---------|-------|
| Words | 6,127 |
| Characters | 29,241 |
| Lines | 338 |

Counted with `wc -w`, `wc -c` and `wc -l`.

## Tokens sent on each call

The whole handbook is sent to the model on every call, so this is the input size per call.

| Method | Tokens |
|--------|--------|
| Rule of thumb (0.75 words per token): 6,127 words | about 8,170 |
| Rule of thumb (4 characters per token): 29,241 characters | about 7,310 |
| **Counted with the `o200k_base` tokenizer (used for this estimate)** | **10,058** |

The handbook has tables and symbols, so it uses more tokens than the rules of thumb suggest.
The tokenizer is OpenAI's public one. It is a close stand-in for `gpt-6-luna`, not an exact match.

## Price per call (model: `gpt-6-luna`, prices from `prices.json`)

| Price type | Rate per 1M tokens | Handbook (10,058 tokens) |
|------------|--------------------|--------------------------|
| Input | $0.10 | $0.001006 |
| Cached input | $0.01 | $0.000101 |
| Cache write | $0.125 | $0.001257 |

Handbook cost only. The document the model reads and its answer (output, $0.50 per 1M) cost extra.
