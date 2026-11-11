# Problem 4: Prompt Caching Cost Comparison

**Model:** `gpt-6-luna` through Portkey (Responses API). The API reported the model as `gpt-6-luna-2026-09-22`.
**Script:** `cache_test.py`. Raw data for all 48 model calls is in `output/cache_test.json`.
**Prices:** from `data/prices.json`, per 1M tokens: input $0.10, cached input $0.01, cache write $0.125, output $0.50.

## 1. How caching was turned on and off

OpenAI caches an exact matching start of the prompt (a "prefix"). `gpt-6-luna` supports `prompt_cache_options.mode`:

| Setup | Settings sent with each request | Expected behavior |
|---|---|---|
| **no_cache** | `prompt_cache_options = {mode: "explicit"}`, no cache breakpoint | Automatic caching is off and nothing is marked for caching, so nothing should be read from or written to the cache |
| **cache** | `prompt_cache_options = {mode: "explicit", ttl: "30m"}`, plus a breakpoint right after the instructions and handbook | The instructions and handbook are cached and reused |

Everything else was identical: the same prompt, handbook, documents, and tools. Both setups sent **exactly 271,438 input tokens**, so caching is the only difference.

### Was the switch reliable? Yes, based on the token counts the API reported

- **no_cache: 0 cached tokens and 0 cache-write tokens on all 24 calls.** This is a strong test. Each document needs 2 model calls, and the second call repeats the first call's ~11,000-token prefix. Under the provider's default (automatic) caching, that second call reads the prefix from the cache, as it did in the Problem 3 runs. In no_cache mode it never did.
- **cache: all 24 calls read exactly 11,080 tokens from the cache.** That is the instructions plus the handbook (the handbook alone is 10,062 tokens; `prompt.md` and its wrapper add about 1,018).
- The provider returned no cache-diagnostic details (`cache_diagnostics` is `null`), so this conclusion rests on the token counts alone. That is enough here, because no_cache never showed a single cached token.

**Caveat (cache writes):** no cache-write tokens were reported in the cache pass either. The handbook prefix was already cached by the Problem 3 runs earlier the same evening and was still live (30-minute minimum lifetime). A real cold start does cost money: the first Problem 3 run reported **11,096 cache-write tokens ($0.00139)**. That one-time cost is added back in the projection in section 4.

## 2. Results: 12 practice documents × 2 setups

| | no_cache | cache |
|---|---|---|
| Documents | 12 | 12 |
| Model calls | 24 (2 per document) | 24 (2 per document) |
| Input tokens | 271,438 | 271,438 |
| …of which read from cache | 0 | 265,920 (98.0%) |
| …of which written to cache | 0 | 0 |
| …of which uncached | 271,438 | 5,518 |
| Output tokens (including reasoning) | 2,801 (1,403 reasoning) | 2,868 (1,419 reasoning) |
| Input cost | $0.027144 | $0.003211 ($0.000552 uncached + $0.002659 cached) |
| Output cost | $0.001401 | $0.001434 |
| **Total cost** | **$0.028544** | **$0.004645** |
| **Average cost per document** | **$0.0023787** | **$0.0003871** |
| **Savings vs no_cache** | — | **$0.023899 (83.7%)** |

Output tokens are nearly the same in both setups. That is expected, because caching changes only how input is billed.

### Per document

| Document | no_cache cost | cache cost | Decision (both setups) | Key |
|---|---|---|---|---|
| p01 Blue Hen | $0.002352 | $0.000358 | recommend | recommend ✅ |
| p02 Elm City | $0.002375 | $0.000412* | recommend | do_not_recommend ❌ |
| p03 Ivy Print | $0.002494 | $0.000471 | do_not_recommend | do_not_recommend ✅ |
| p04 Harbor Stitch | $0.002360 | $0.000370 | recommend | recommend ✅ |
| p05 Maple Leaf | $0.002347 | $0.000366 | do_not_recommend | do_not_recommend ✅ |
| p06 Quinnipiac | $0.002360 | $0.000370 | do_not_recommend | do_not_recommend ✅ |
| p07 Long Wharf | $0.002402 | $0.000442 | recommend | do_not_recommend ❌ |
| p08 Chapel St | $0.002376 | $0.000379 | recommend | recommend ✅ |
| p09 Westville | $0.002349 | $0.000379 | do_not_recommend | do_not_recommend ✅ |
| p10 East Rock | $0.002344 | $0.000354 | recommend | recommend ✅ |
| p11 York St | $0.002410 | $0.000356 | do_not_recommend | do_not_recommend ✅ |
| p12 Blue Hen | $0.002376 | $0.000387 | recommend | do_not_recommend ❌ |

\* p02's first cached attempt timed out (two 90-second attempts). It was rerun once and the rerun was recorded. The failed attempt is marked in `cache_test.json`. The API returned no usage data for it, so if the provider billed anything for it, that cost is not counted here.

- **Caching did not change any decision.** Both setups gave the same answer on all 12 documents, and both scored 9 of 12 against the key.
- The three misses (p02, p07, p12) are the Problem 3 prompt weakness: the agent trusts "revised price" and "correction" notes inside the document. It is unrelated to caching.

## 3. Comparison with the Problem 2 estimate

Problem 2 priced **one call carrying only the handbook (10,058 tokens)**.

| Per document | Problem 2 estimate | Actual | Actual ÷ estimate |
|---|---|---|---|
| Without caching | $0.0010058 | $0.0023787 | 2.36× |
| With caching (warm cache) | $0.0001006 | $0.0003871 | 3.85× |
| Savings from caching | ~90% | 83.7% | — |

### Why the actual costs differ from the estimate

1. **Two model calls per document, not one.** The agent first calls the model to decide to use `read_document`, then calls it again with the document text to give its answer. The handbook goes out with both calls, so about 22,600 input tokens per document instead of 10,058. This alone explains about 2.2× of the gap.
2. **The prompt is more than the handbook.** Each call also carries `prompt.md` (about 1,000 tokens), the tool definitions, the user message, and on the second call the document text and tool call. That comes to 11,222 to 11,408 input tokens per call.
3. **Output tokens were not in the estimate.** About 117 to 120 output tokens per call, about half of them hidden reasoning, at $0.50 per 1M. That adds about $0.00012 per document. It barely matters without caching (5% of the cost) but is **31% of the cached cost**.
4. **Not everything can be cached.** Only the shared 11,080-token prefix is cached. The 142 to 328 tokens after it (the document, the tool result, the user message) differ for each document and are always billed at the full $0.10 rate.
5. **Savings are 83.7% instead of 90%.** Problem 2 assumed the only cost was cacheable input. Output tokens and the uncached tail are not discounted, so the savings percentage is lower. With caching, the bill is roughly 57% cache reads, 31% output, and 12% uncached input.
6. **No cache-write charge was observed.** Problem 2 included one cache write at $0.125 per 1M. Here the cache was already warm from earlier runs, so the write was not charged in this test (see section 1). It is added back below.

## 4. Projection: 1,000 documents per day for 30 days (30,000 documents)

| Scenario | Calculation | 30-day cost |
|---|---|---|
| **Actual, no caching** | 30,000 × $0.0023787 | **$71.36** |
| **Actual, with caching** (reads only) | 30,000 × $0.0003871 | $11.61 |
| + cache writes, best case (1 write per day) | 30 × 11,080 × $0.125 / 1M | + $0.04 |
| + cache writes, worst case (cache expires every 30 minutes, 48 writes per day) | 1,440 × $0.001385 | + $1.99 |
| **Actual, with caching, total** | | **$11.65 to $13.60** |
| **Savings from caching** | | **about $58 to $60 per month (81% to 84%)** |
| Problem 2 estimate, no caching | 30,000 × $0.0010058 | $30.17 |
| Problem 2 estimate, with caching | 30 × (1 write + 999 reads per 1,000 calls) | $3.05 |

- At 1,000 documents a day the cache rarely goes cold. Even spread over 24 hours that is one document about every 86 seconds, far inside the 30-minute cache lifetime. So the realistic cached cost is close to **$11.65 per month**.
- The Problem 2 estimate understates the real monthly bill by about 2.4× without caching and 3.8× with caching, because it priced only one call and only the handbook.
- **Budget planning should use the measured figures:** about **$0.0024 per document without caching** and about **$0.0004 with caching**.

## 5. Limitations

- **Portkey response cache (found during Problem 5):** Portkey's own response cache is on for this API key. If a request is byte-for-byte identical to an earlier one, Portkey returns the saved response (`x-portkey-cache-status: HIT`) without calling the model. In this test, the **p01 records in both setups were replays** of the single-document trial run made just before (identical token counts, both calls within one second). All other 22 documents were new requests and were answered by the model. A replay carries the original call's token counts, so the per-document costs above still describe a real `gpt-6-luna` call. The trial calls they replay also showed 0 cached tokens with caching off. Future reruns should send `x-portkey-cache-force-refresh: true`, as `attack_test.py` now does.

- **Prompt changed after this test:** the Problem 3 prompt fix, made after these runs, added about 245 input tokens to each call, about 490 per document. Without caching that adds about $0.00005 per document (about 2%). With caching, the extra tokens become part of the cached prefix, so the effect is even smaller. The first run after the change paid a real cache write of 11,524 tokens ($0.00144), which matches the cold-start cost used in section 4.

- **Small sample:** 12 documents per setup, each run once. Costs per document varied by only about ±6% (no_cache $0.00234 to $0.00249), so the averages are stable, but output length can vary from run to run.
- **Cache writes estimated, not measured in this pass:** the cache-write cost comes from the Problem 3 cold-start run (11,096 tokens), because the cache was already warm when the cached pass ran.
- **No provider diagnostics:** the Portkey/Azure route did not return cache diagnostics, so whether caching was on or off was confirmed only from the token counts in the usage data.
- **Prices:** these are the `prices.json` list prices. Portkey's own fees and any billing for the timed-out p02 attempt are not included.
