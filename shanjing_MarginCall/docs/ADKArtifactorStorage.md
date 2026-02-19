# ADK Artifact Storage: Benefits and Location

## Summary

| Aspect | Answer |
|--------|--------|
| **Location** | Depends on implementation: **InMemoryArtifactService** = local RAM; **GcsArtifactService** = Google Cloud Storage (cloud) |
| **Benefits** | Versioned binary storage, session/user namespacing, avoids cluttering session state |
| **MarginCall** | Uses **local cache** (SQLite) for charts instead of ADK artifacts |

---

## Where is ADK Artifact Storage Located?

ADK provides pluggable artifact service implementations:

| Implementation | Location | Persistence |
|----------------|----------|-------------|
| **InMemoryArtifactService** | Local process RAM | Ephemeral—lost when process exits |
| **GcsArtifactService** | Google Cloud Storage bucket | Persistent, cloud-hosted |

You configure which one to use when creating the Runner:

```python
# Local (RAM, dev/testing)
artifact_service = InMemoryArtifactService()

# Cloud (GCS, production)
artifact_service = GcsArtifactService(bucket_name="my-bucket", storage_client=...)

runner = Runner(
    agent=agent,
    app_name="my_app",
    session_service=session_service,
    artifact_service=artifact_service,  # Can be None if not used
)
```

- **Cloud**: GCS bucket path is typically `gs://bucket/app_name/user_id/session_id/artifact_filename`
- **Local**: Stored in-memory; no disk persistence unless you use a custom implementation

---

## Benefits of ADK Artifact Storage

1. **Handles large binary data**  
   Session state is for small config/conversation data; artifacts are for files, images, PDFs.

2. **Versioning**  
   Each `save_artifact` call creates a new version; you can load specific versions.

3. **Namespacing**
   - **Session-scoped** (default): `filename` → tied to `app_name`, `user_id`, `session_id`
   - **User-scoped**: `"user:filename"` → tied to `app_name`, `user_id`, shared across sessions

4. **Separation of concerns**  
   Binary blobs stay in artifact storage, not in session state or tool return values, so they are not sent to the LLM unless explicitly loaded.

5. **Standardized interface**  
   Same API regardless of backend (in-memory vs GCS).

---

## Why MarginCall Uses Local Cache Instead

MarginCall stores charts in the **local SQLite cache** rather than ADK artifacts:

1. **No LLM bloat**  
   Tool return values with base64 images go into the agent context. Stripping base64 from the return value and storing charts in cache keeps LLM context small.

2. **Frontend access**  
   `/api/charts` reads from the cache. No artifact service needed for the web UI.

3. **Single source of truth**  
   Cache stores price, financials, technicals, and charts together. Cache invalidation (`invalidate_cache`) works uniformly.

4. **Local-first**  
   All fetch_ tools (except news) run and store data locally; no cloud artifact service required for development.

---

## When to Use ADK Artifacts

Consider ADK artifact storage when:

- You need **user-uploaded files** (e.g. PDFs for analysis)
- You want **versioned, persistent** binary output (e.g. generated reports)
- You deploy to **Cloud Run / Agent Engine** and use GCS
- You need **session vs user** scoping for binary data

For chart images in MarginCall, local cache is sufficient and avoids extra dependencies.

reference:
          "functionResponse": {
            "name": "fetch_technicals_with_chart",
            "response": {
              "ticker": "IREN",
              "charts": {
                "1y": {
                  "label": "1-Year Daily",
                  "image_base64": "iVBORw0KGgoAAAANSUhEUgAACWAAAAcICAYAAAC41foEAAAQAEl... 500KB