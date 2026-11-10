# Cache Test (Problem 4)

Model `gpt-6-luna` only. Same agent, same 12 practice docs, two setups. Every model call is in `cache_test.json` (48 calls: 2 per doc per setup). Dollars come from `prices.json`.

- **no_cache**: a random ID goes at the very top of the prompt on every model call, so nothing can be reused.
- **cache**: the normal agent, with the same handbook prefix on every call.

## Tokens reported by the API (all 12 docs)

| Setup | Input | Cache read | Cache write | Output |
|---|---|---|---|---|
| no_cache | 266,196 | 0 | 263,172 | 2,641 |
| cache | 265,538 | 249,564 | 12,950 | 2,524 |

Input includes the cache read and cache write tokens.

## Cost

| Setup | Total (12 docs) | Per document |
|---|---|---|
| no_cache | $0.034519 | $0.002877 |
| cache | $0.005679 | $0.000473 |

**Saved with caching: 83.5%**

### Cost per document

| Document | no_cache | cache |
|---|---|---|
| p01_bluehen_quote.html | $0.002865 | $0.001607 |
| p02_elmcity_quote.html | $0.002883 | $0.000386 |
| p03_ivyprint_catalog.html | $0.002935 | $0.000431 |
| p04_harborstitch_quote.html | $0.002874 | $0.000386 |
| p05_maplemills_quote.pdf | $0.002861 | $0.000347 |
| p06_qtextile_quote.pdf | $0.002844 | $0.000344 |
| p07_longwharf_quote.pdf | $0.002890 | $0.000389 |
| p08_chapelst_email.eml | $0.002880 | $0.000347 |
| p09_westville_email.eml | $0.002858 | $0.000354 |
| p10_eastrock_email.eml | $0.002874 | $0.000362 |
| p11_yorkst_quote.html | $0.002889 | $0.000367 |
| p12_bluehen_quote.pdf | $0.002867 | $0.000358 |

Note: the API still reported cache-write tokens on the no_cache calls (the unique prefix is written to the cache but never read), and `prices.json` charges cache writes at $0.125 per 1M, more than plain input at $0.10. If those tokens were billed as plain input instead, no_cache would total $0.027940 and caching would save 79.7%.

## Compared with the Problem 2 table

Problem 2 priced the handbook alone (10,058 tokens): $0.001006 per call at the input rate, $0.000101 per call at the cached rate. With 2 calls per doc:

| | Problem 2 estimate (handbook only) | Measured here | Measured / estimate |
|---|---|---|---|
| Per doc, no cache | $0.002012 | $0.002877 | 1.43x |
| Per doc, cache | $0.000201 | $0.000473 | 2.35x |
| Saving from caching | 90.0% | 83.5% | |

The measured numbers are higher because each call also carries `prompt.md`, the tool definitions and the document text, the model writes an answer (output costs $0.50 per 1M), no_cache calls pay the cache-write rate, and the first cache call (p01_bluehen_quote.html) was a cold start that wrote the whole prompt. Per doc, cache after the cold start: $0.000370.

## Projection: 1,000 docs a day for 3 days (3,000 docs)

| Basis | Per day (1,000 docs) | 3 days (3,000 docs) |
|---|---|---|
| Measured, no cache | $2.88 | $8.63 |
| Measured, cache | $0.47 | $1.42 |
| Measured, cache (warm, after cold start) | $0.37 | $1.11 |
| Problem 2 estimate, no cache | $2.01 | $6.03 |
| Problem 2 estimate, cache | $0.20 | $0.60 |

Measured saving over 3 days: $7.21 (83.5%).
Projection assumes the average of these 12 docs holds, and that the cache stays warm (calls come close together; the API drops cached prompts after a short idle time).
