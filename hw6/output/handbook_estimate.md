# Problem 2: Handbook Token and Cost Estimate

## Inputs

- **Document:** `data/shop_handbook.md`, unzipped from `data.zip`. It has 338 lines, 6,127 words, 28,903 characters, and 29,241 bytes.
- **Model:** `gpt-6-luna`, routed through Portkey.
- **Prices**, from `data/prices.json` ("OpenAI Standard pricing, per 1M tokens (MGT 409 Lecture 11)"):

| Price type | USD per 1M tokens |
|---|---|
| Input (uncached) | $0.10 |
| Cached input (cache read) | $0.01 |
| Cache write | $0.125 |
| Output | $0.50 |

## Token count

**Handbook = 10,058 tokens**

### How it was counted

I tokenized the full handbook text with OpenAI's `tiktoken` library and counted the tokens:

```python
import tiktoken
text = open("data/shop_handbook.md", encoding="utf-8").read()
tokens = tiktoken.get_encoding("o200k_base").encode(text)
print(len(tokens))   # 10058
```

- `tiktoken` has no mapping for `gpt-6-luna` yet. So I used `o200k_base`, the tokenizer that `tiktoken` uses for current OpenAI models such as `gpt-4o` and `gpt-5`. I'm assuming `gpt-6-luna` uses the same tokenizer.
- **Cross-check:** the older `cl100k_base` tokenizer gives 10,184 tokens, about 1% more. The common rule of thumb of about 4 characters per token gives 28,903 / 4 ≈ 7,226 tokens. That rule undercounts this file because the file has many tables, codes, numbers, and punctuation, which split into more tokens.
- On average the file comes to about 2.9 characters per token, or 1.64 tokens per word.

### Verified with a live API call

`verify_tokens.py` made two small `gpt-6-luna` calls through Portkey. The API reported the model as `gpt-6-luna-2026-09-22`.

| Call | `usage.prompt_tokens` |
|---|---|
| Handbook as system message + "Reply with OK." | 10,072 |
| "Reply with OK." only (baseline) | 10 |
| **Difference: handbook as sent** | **10,062** |

The `tiktoken` count was 10,058. The extra 4 tokens wrap the system message, so the `o200k_base` assumption is confirmed. Every cost below uses 10,058. Using 10,062 or 10,072 changes the 1,000-call totals by less than half a cent.

## Cost calculations

Formula: **cost = tokens × (price per 1M) / 1,000,000**

### Without caching (every call pays the full input price)

| Scenario | Calculation | Cost |
|---|---|---|
| 1 call | 10,058 × $0.10 / 1,000,000 | **$0.0010058** (about 0.1¢) |
| 1,000 calls | $0.0010058 × 1,000 | **$1.0058** |

### With caching

| Scenario | Calculation | Cost |
|---|---|---|
| 1 call, first call (cache write) | 10,058 × $0.125 / 1,000,000 | **$0.0012573** |
| 1 call, cache already warm (cache read) | 10,058 × $0.01 / 1,000,000 | **$0.0001006** |
| 1,000 calls (1 write + 999 reads) | $0.0012573 + 999 × $0.0001006 | **$0.1017** |
| 1,000 calls, all cache reads (cache warmed earlier) | 1,000 × $0.0001006 | **$0.1006** |

### Comparison for 1,000 calls

| | Cost | vs. uncached |
|---|---|---|
| No caching | $1.0058 | — |
| With caching (1 write + 999 reads) | $0.1017 | saves $0.9041 (about 89.9%) |

The first cached call costs 25% more than an uncached call because of the cache-write price. After that, each cached call costs one-tenth of the full input price. Caching already saves money by the second call: $0.0012573 + $0.0001006 = $0.0013579, compared with $0.0020116 uncached.

## Assumptions

1. The cost covers only the handbook as input tokens. Output tokens ($0.50 per 1M), the user's question, the vendor document, and the few tokens of chat formatting added to each message are all excluded.
2. `gpt-6-luna` uses the `o200k_base` tokenizer. The live API check above confirmed this to within 4 tokens.
3. In the cached case the whole handbook is cached. For that to happen, the handbook must be sent as the identical first part of every prompt (for example, the system prompt), and it must be longer than the provider's minimum cacheable length (OpenAI's is 1,024 tokens).
4. The cache stays warm across all 1,000 calls. In practice a cache expires after a period of inactivity, so calls spread out over time would pay the cache-write price again. The real cost would then fall between $0.10 and $1.01.
5. Prices are taken exactly as listed in `prices.json`. Portkey's own fees, taxes, and volume discounts are not included.
