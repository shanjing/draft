# MarginCall test suite

- **`conftest.py`** — Shared fixtures: mocks and fake data sources (e.g. `noop_cache`, `tmp_cache`, `mock_yfinance`, `mock_requests_get`). These simulate real APIs and the cache so tests don’t hit the network or production DB. Tests request fixtures by name as function arguments.

- **`test_*.py`** — Test modules. Each test runs against those fixtures, calls the code under test, and **verifies** results: return shape (`status`, `price`, `ticker`), error payloads, cache read/write behavior (roundtrip, TTL, invalidation), and types.

- **`pytest.ini`** (project root) — Optional pytest config: `testpaths`, `asyncio_mode`, warnings. Pytest discovers tests by convention (`test_*.py`, `test_*` functions); the `.ini` only customizes how they run.

## Run tests

From project root:

```bash
pytest
pytest tests/test_cache.py
pytest -v -k "test_put_get"
```
