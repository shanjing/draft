**Testing layers:**
  - Unit tests (pytest): schemas, cache, tools, truncation — runs offline, no API keys
  - Smoke test (check_env.py): agent wiring, imports, config validation
  - Manual integration: python -m main run -i "analyze GOOGL" — verifies full pipeline
  - Future: eval framework for output quality scoring, token budget assertions