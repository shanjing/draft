## Caching Strategy

Goal:
Cache artifacts and data locally so that repeat requests within 24 hours serve from cache instead of re-fetching everything.

User asks "Analyze AAPL"

```
        │
        ▼
  Cache Lookup (by ticker + date)
  ┌──────────────────────────┐
  │ Is there a cached report  │
  │ for AAPL within 24hrs?   │
  ├──────┬───────────────────┤
  │ YES  │        NO         │
  │      │                   │
  │  Serve from     Run full pipeline
  │  local cache    Save to cache
  │      │                   │
  └──────┴───────────────────┘
```

### SQLite Cache Index (cache.db)

```sql
CREATE TABLE cache_entries (
    id          INTEGER PRIMARY KEY,
    ticker      TEXT NOT NULL,
    cache_date  TEXT NOT NULL,           -- YYYY-MM-DD
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at  DATETIME NOT NULL,       -- created_at + 24hrs
    cache_path  TEXT NOT NULL,           -- e.g., "artifacts/AAPL/2026-02-07/"
    data_type   TEXT NOT NULL,           -- "stock_data" | "sentiment" | "news" | "report" | "chart"
    status      TEXT DEFAULT 'valid',    -- "valid" | "expired" | "stale"
    UNIQUE(ticker, cache_date, data_type)
);

CREATE INDEX idx_ticker_date ON cache_entries(ticker, cache_date);
CREATE INDEX idx_expires ON cache_entries(expires_at);
```

### Future backend:
Redis: cache_key → Redis key, data → Redis value, ttl_seconds → EXPIRE
GCS: cache_key → object name, data → object body, metadata → custom metadata



### The Right Pattern: Cache Interface + Pluggable Backends

```
tool functions (fetch_vix, fetch_financials, etc.)
        │
        ▼
  CacheInterface (abstract)        ← stable contract
        │
        ├── LocalSQLiteBackend     ← now (development)
        ├── RedisBackend           ← later (multi-instance)
        └── GCSBackend             ← later (cloud, ADK-native)
```

### Interface Design

```python
class CacheBackend(ABC):
    """All backends implement this contract."""

    async def get(self, key: str) -> bytes | None: ...
    async def put(self, key: str, data: bytes, ttl_seconds: int): ...
    async def delete(self, key: str): ...
    async def exists(self, key: str) -> bool: ...
```

Key insight: **the cache key and serialization stay the same** regardless of backend. Only the storage layer changes.

### Key Design Decisions

| Decision | Recommendation | Why |
|----------|---------------|-----|
| **Key format** | `{ticker}:{data_type}:{date}` e.g. `AAPL:financials:2026-02-07` | Works for any backend (SQLite key, Redis key, GCS object name) |
| **Data format** | JSON bytes for data, raw bytes for artifacts | Universal — every backend can store bytes |
| **TTL enforcement** | Backend-native when possible | SQLite: query `expires_at`, Redis: built-in TTL, GCS: lifecycle rules |
| **Metadata vs data** | Store together in one record | Simpler than SQLite index + separate files; GCS has object metadata |
| **Async** | Yes, async from day 1 | SQLite: `aiosqlite`, Redis: `aioredis`, GCS: `gcloud-aio-storage` |

### Migration Path

| Phase | Backend | When | What Changes |
|-------|---------|------|-------------|
| **Now** | SQLite (local) | Development | Build `CacheBackend` interface + `SQLiteCacheBackend` |
| **Phase 2** | Redis (Memorystore) | Multi-instance on Cloud Run | Swap to `RedisCacheBackend`, same interface |
| **Phase 3** | GCS + ADK ArtifactService | Production cloud | Swap to `GCSCacheBackend`, charts go to GCS buckets |
| **Phase 4** | Tiered | Scale | Redis for hot data (price, sentiment) + GCS for cold (charts, reports) |

### SQLite Schema (Built for Migration)

```sql
CREATE TABLE cache (
    cache_key    TEXT PRIMARY KEY,         -- "AAPL:financials:2026-02-07"
    data         BLOB NOT NULL,            -- JSON bytes or binary
    mime_type    TEXT DEFAULT 'application/json',
    ttl_seconds  INTEGER NOT NULL,
    created_at   REAL NOT NULL,            -- unix timestamp
    expires_at   REAL NOT NULL,            -- unix timestamp
    ticker       TEXT,                     -- indexed for bulk invalidation
    data_type    TEXT                      -- "price" | "chart_1y" | "report" etc.
);

CREATE INDEX idx_expires ON cache(expires_at);
CREATE INDEX idx_ticker ON cache(ticker);
```

This maps cleanly to every future backend:
- **Redis**: `cache_key` → Redis key, `data` → Redis value, `ttl_seconds` → `EXPIRE`
- **GCS**: `cache_key` → object name, `data` → object body, metadata → custom metadata

### What NOT to Do

| Anti-pattern | Why it hurts migration |
|-------------|----------------------|
| File paths in cache keys | GCS uses flat namespace, not filesystem paths |
| SQLite-specific queries in tool code | Tools should only call `cache.get()` / `cache.put()` |
| Storing charts as separate files alongside SQLite | Forces a storage convention that doesn't exist in Redis/GCS |
| Hardcoding TTLs in the backend | TTLs belong in the tool layer (business logic), not storage layer |

### ADK GCS Artifact Service Compatibility

ADK's `ArtifactService` uses GCS buckets with the pattern:
```
gs://bucket/app_name/user_id/session_id/artifact_name
```

Cache keys can coexist by using a different prefix:
```
gs://bucket/cache/{ticker}/{data_type}/{date}
```

When migrate to GCS, implement `GCSCacheBackend` that writes to the `cache/` prefix, separate from ADK's artifact namespace.

### Revised File Structure

```
tools/
├── cache/
│   ├── __init__.py              # Exports get_cache_backend()
│   ├── base.py                  # CacheBackend ABC
│   ├── sqlite_backend.py        # Local dev backend
│   ├── redis_backend.py         # (future) Multi-instance
│   └── gcs_backend.py           # (future) Cloud production
├── config.py                    # Add CACHE_BACKEND="sqlite" setting
└── ...
```

Config-driven backend selection:
```python
# tools/config.py
CACHE_BACKEND = os.getenv("CACHE_BACKEND", "sqlite")  # "sqlite" | "redis" | "gcs"
```

### Effort (Revised)

| Task | Days |
|------|------|
| `CacheBackend` ABC + `SQLiteCacheBackend` | 1 |
| `@cached` decorator with TTL tiers | 0.5 |
| Wrap all data tools with caching | 1 |
| Chart artifact caching (binary blobs in SQLite) | 0.5 |
| Config + backend selection | 0.5 |
| Testing | 0.5 |
| **Total** | **~4 days** |

Future backends (Redis, GCS) are ~0.5-1 day each since the interface is already defined.

### Bottom Line

Build the **abstract interface now**, implement **SQLite only**. When move to Cloud Run, swap in Redis/GCS by changing one env var. The tool functions never change — they just call `cache.get()` and `cache.put()`.
