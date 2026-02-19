[5 tools called]

Now let me read the tool files to understand their signatures:

[4 tools called]

Now I have full context. Let me build the cache system.

[9 tools called]

Now wrap all 7 tool functions with the `@cached` decorator:

[11 tools called]

Now create the `invalidate_cache` tool function for the root agent's refresh flow:

[2 tools called]

Now update the root agent to support the refresh flow:

[7 tools called]

Now let me test the full cache system:

[1 tool called]

All 6 core cache tests pass. Now let me test the decorator integration with actual tool functions:

[1 tool called]

All tests pass. The cache shows **2428x speedup** on the second call for `fetch_stock_price` and **688x** for `fetch_vix`. Let me also add cache entries to `.gitignore` and verify there are no remaining lint issues:

[2 tools called]

Good -- `*.db` is already in `.gitignore` so `MarginCall_cache.db` is covered. Let me also check the `fetch_technicals_with_chart.py` since it's an async function that uses `generate_trading_chart`. It should also be cached, but its composite nature (calling `generate_trading_chart` internally which creates artifacts) needs slightly different handling. Let me read the current state:

[2 tools called]

The `fetch_technicals_with_chart` is async and needs special handling for chart artifacts. Let me add caching directly in it rather than using the decorator, since we need to cache chart binary data and re-inject into `tool_context`:

[2 tools called]

Now let me update the `__init__.py` for the cache package to also export the decorators:

[1 tool called]

Now let me check all linter errors:

[4 tools called]

Clean. Let me do a final comprehensive test to make sure imports resolve and everything ties together:

[1 tool called]

All imports resolve, signatures are preserved for ADK, and the root agent builds correctly.

[1 tool called]

Here's a summary of everything implemented:

---

## Cache System Implementation

### New files created

**`tools/cache/base.py`** — Abstract `CacheBackend` interface with 7 methods: `get`, `put`, `delete`, `exists`, `invalidate_ticker`, `purge_expired`, `close`, plus a `make_key()` helper. Any future backend (Redis, GCS) implements this contract.

**`tools/cache/sqlite_backend.py`** — `SQLiteCacheBackend` with:
- Separate DB at `cache/MarginCall_cache.db` (not mixed with ADK's session DB)
- WAL journal mode for better concurrent read/write
- **Auto-purge**: expired entries are cleaned every 5 minutes on any `get()` call
- Indexes on `expires_at`, `ticker`, and `(ticker, data_type)` for fast lookups
- `get_json()` / `put_json()` convenience methods for dict serialization

**`tools/cache/decorators.py`** — `@cached` decorator with:
- **3 TTL tiers**: `TTL_REALTIME` (15 min), `TTL_INTRADAY` (4 hours), `TTL_DAILY` (24 hours)
- Works with both sync and async functions
- Handles functions with/without ticker parameter
- Adds `_from_cache: True` flag to cached results
- Only caches successful responses (not errors)

**`tools/cache/__init__.py`** — Singleton `get_cache()` factory. Also includes a `_NoOpCacheBackend` used when `CACHE_DISABLED=true`.

**`agent_tools/invalidate_cache.py`** — Tool function the root agent calls to clear all cached data for a ticker before re-running the pipeline with fresh data.

### Files modified

| File | Change | TTL |
|------|--------|-----|
| `agent_tools/fetch_stock_price.py` | `@cached(data_type="price")` | 15 min |
| `agent_tools/fetch_financials.py` | `@cached(data_type="financials")` | 24 hours |
| `agent_tools/fetch_technical_indicators.py` | `@cached(data_type="technicals")` | 24 hours |
| `agent_tools/fetch_technicals_with_chart.py` | Inline cache check + put | 24 hours |
| `agent_tools/fetch_vix.py` | `@cached(data_type="vix")` | 4 hours |
| `agent_tools/fetch_stocktwits_sentiment.py` | `@cached(data_type="stocktwits")` | 4 hours |
| `agent_tools/fetch_cnn_greedy.py` | `@cached(data_type="cnn_fear_greed")` | 4 hours |
| `tools/config.py` | Added `CACHE_BACKEND` and `CACHE_DISABLED` env vars |
| `stock_analyst/agent.py` | Added `invalidate_cache` tool + refresh instructions |

### How the refresh flow works

- **Normal request** ("Analyze AAPL"): Pipeline runs, tools return cached data if available (2400x faster)
- **Real-time request** ("Refresh AAPL", "Get live data for TSLA"): Root agent calls `invalidate_cache(ticker)` first to clear all cached entries for that ticker, then runs the pipeline with fresh API calls
- **Auto-purge**: Every 5 minutes, any cache read sweeps expired entries. No cron needed.

### Future scalability

The `CacheBackend` ABC is designed for drop-in replacement:
- `SQLiteCacheBackend` — now (local dev)
- `RedisCacheBackend` — future (cloud, sub-ms reads)
- `GCSCacheBackend` — future (ADK artifact service integration)

Just change `CACHE_BACKEND=redis` in `.env` and wire up the factory.