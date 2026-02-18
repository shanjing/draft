# Frontend–Backend Connection & ADK’s Role

Short memo: how the uvicorn server ties the frontend to the backend and how ADK fits in.

---

## Single process, one FastAPI app

**Uvicorn** runs a single FastAPI application (`server:app`). That app is the whole “backend”: it serves both the **agent API** (from ADK) and the **custom frontend** (static files + project-specific APIs).

- **Start:** `uvicorn server:app --host 0.0.0.0 --port 8080`
- **Entry:** `server.py` builds the app, mounts routes, then uvicorn serves it.

There is no separate “frontend server” and “backend server.” The browser talks to one origin (e.g. `localhost:8080`); all requests go to this one process.

---

## How the frontend reaches the backend

1. **Static UI**  
   The app mounts the `frontend/` directory at `/`. So `GET /` returns `index.html`; `app.js`, `styles.css`, etc. are loaded from the same host. No CORS or second origin.

2. **Agent and sessions (ADK)**  
   The frontend uses HTTP APIs that **ADK’s FastAPI integration** provides on that same app:
   - `POST /apps/{appName}/users/{userId}/sessions` → create session  
   - `GET /apps/{appName}/users/{userId}/sessions/{sessionId}` → read session (including `state`, e.g. `stock_report`)  
   - `POST /run_sse` → run the agent and stream events (SSE)

   So the “backend” for chat and session state is the **ADK API** mounted into this app.

3. **Project-specific APIs**  
   `server.py` adds its own router with:
   - `GET /api/charts?ticker=...` → chart images (from cache) for the report UI  
   - `GET /api/log_stream` → SSE stream of server logs for the log panel  

   Same host, same app; the frontend calls these like any other API.

So: **one base URL, one app**. Frontend (HTML/JS/CSS) and backend (ADK + custom routes) are separated by **responsibility and URL path**, not by separate processes or ports.

---

## ADK’s role

- **Provides the agent runtime and HTTP API**  
  `get_fast_api_app(agents_dir=..., session_service_uri=..., ...)` (from `google.adk.cli.fast_api`) returns a FastAPI app that already includes:
  - Session create/read (and any other session endpoints the ADK server exposes)
  - `POST /run` and `POST /run_sse` to execute the agent and stream events

- **Defines the contract**  
  Request/response shapes (e.g. `app_name`, `user_id`, `session_id`, `new_message`, `streaming`) and the event stream format are defined by ADK. The frontend is written to that contract.

- **Backend logic lives in agents**  
  All agent logic (stock_analyst, pipeline, tools, session state) is in the MarginCall codebase; ADK does not implement business logic. It provides the **runtime and the HTTP layer** that the frontend calls.

So ADK’s role is: **supply the FastAPI app and routes that expose the agent and sessions; the project then extends that app with custom routes and serves the frontend.**

---

## Clean separation of frontend and backend

| Layer | What it is | Where it lives |
|-------|------------|----------------|
| **Frontend** | UI and client behavior | `frontend/`: static HTML, CSS, JS. No server code; only consumes APIs. |
| **Backend – ADK** | Agent execution, sessions, `/run`, `/run_sse`, session CRUD | In process via `get_fast_api_app()`; contract is ADK’s. |
| **Backend – custom** | Charts API, log stream, any other app-specific HTTP | `server.py`: `APIRouter` mounted on the same `app`. |

Separation is achieved by:

1. **API boundary**  
   The frontend only uses documented HTTP endpoints. It does not depend on Python or ADK internals.

2. **Single app, multiple concerns**  
   ADK owns agent/session routes; the project owns `/api/*` and static files. Both are mounted on one `app`, so deployment stays one process (e.g. one uvicorn, one container).

3. **Data contract**  
   Session state (e.g. `stock_report`) and event stream shape are the contract between backend and frontend. The frontend uses `getSessionState()` and the SSE payload; the backend (agents + ADK) fills session state and events.

4. **No backend in the frontend bundle**  
   `frontend/` has no server, no direct ADK/agent imports. It only does `fetch()` to the same origin. So “frontend” = static assets + API client; “backend” = FastAPI app (ADK + custom routes) plus agent code.

In short: **uvicorn serves one FastAPI app that combines ADK’s agent API and custom routes; the frontend is static files on that same app and talks to the backend only over HTTP.** ADK provides the agent/session API; the project adds custom APIs and the UI, keeping a clear frontend/backend split by responsibility and API boundary.
