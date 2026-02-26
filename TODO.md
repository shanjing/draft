1. Add X support — fetch and store X posts.
2. Accept browser plugin bookmark-style drops into the source box in the UI.
3. Encryption on vault-guarded files.
4. API encryption for MCP (later).
5. Expose the project as an MCP server for agents.
6. In **setup.sh**: when the user skips AI (no API key), show "Draft still works well with index/search; only AI assistance is disabled."
7. *** **setup.sh** should detect new vs existing install — new = all doc sources empty; existing = **~/.draft/.doc_sources** and vault already have files.
8. *** **setup.sh** should check consistency between **sources.yaml**, **~/.draft/.doc_sources**, and vault.

--- setup.sh / UX ---
9. *** **setup.sh** re-run: detect new vs existing install. For existing, show current state (sources, vault, LLM config, RAG index) and offer targeted prompts (add more? reconfigure LLM? rebuild RAG? start UI?) instead of full wizard.
10. "Other" model: parse **provider:model** (e.g. **openai:gpt-4**) and call **setup_env_writer** with the correct mode (or add a custom/other mode). Fix confirmation text so it does not say "Ollama" when the user entered a non-Ollama string.
11. **setup.sh**: rationalize **set -e** vs **|| true** — document which steps are must-fail vs best-effort; avoid **|| true** on the critical path (verify, add source, LLM write).
12. RAG prompt: reword "RAG/index is required" so it is clear building now is optional (e.g. "Build RAG/index now? You can also do this later from the UI.").
13. Write **.draft-ui.log** under **DRAFT_HOME** (**~/.draft**), not repo root; update serve/start path if needed.
14. **setup.sh** non-interactive: add **--yes**, **--skip-sources**, **--no-llm**, **--no-rag**, **--no-start-ui** (and/or **DRAFT_SETUP_YES**). When non-TTY or **--yes**, use safe defaults and skip read prompts.



15. **RAG Step 2 Plan: add codebase to the vector DB for semantic Q&A**

Goal
Answer the question from context (docs + code).
Show citations as links (open in doc viewer).
For code, show file path, line range, and a short snippet in the citation block.
Current state
RAG indexes only .md (via collect_chunks → chunk_markdown). No .py or other code.
Chunks have repo, path, heading, text; no line numbers.
Citations are [{repo, path, heading}]; UI turns them into links that call loadDoc(repo, path).
Doc viewer only allows .md, .txt, .pdf, .doc, .docx. .py is not viewable today.
So we need to: (1) index code, (2) attach line ranges (and optionally snippets) to citations, (3) show links + snippets in the UI.
Plan
1. Index source code (e.g. .py) for RAG
Where: lib/ingest.py (and any shared “what to index” list).
What: In addition to .md, scan .py (and optionally .yaml / .toml for config) under the same effective roots, with the same exclusions and .gitignore.
Chunking: Add a code chunker (e.g. in lib/chunking.py) that splits Python by top-level def/class so each chunk is one or a few definitions. Each chunk gets:
repo, path, heading (e.g. function or class name), text (the code),
start_line, end_line (1-based or 0-based, consistently).
Storage: Put start_line and end_line into Chroma metadata for those chunks (markdown chunks can omit or use 0). Existing repo/path/heading/text stay as they are.
Result: Queries like “testing strategy for evaluating LLMs” can retrieve both doc chunks and code chunks (e.g. from tests/eval_llm.py), so the model can base the answer on both.
2. Citations: include line range and snippet
Where: lib/ai_engine.py (where citations are built and yielded).
Schema: Extend each citation to something like:
repo, path, heading (unchanged),
start_line, end_line (optional; only for code chunks),
snippet (optional; a few lines of code for display).
Snippet source: When building citations, for any chunk that has start_line/end_line:
Resolve the file from the effective repo root (same as doc viewer),
Read the file and slice that line range,
Attach the string as snippet (and keep start_line/end_line for the UI).
Fallback: If the file can’t be read (missing path, not under effective root), leave snippet empty but still send repo/path/start_line/end_line so the UI can at least show “file X, lines Y–Z”.
3. Doc viewer: allow opening code files
Where: ui/app.py (and any shared constant for “allowed extensions”).
Change: Add .py (and optionally .yaml, .toml) to ALLOWED_DOC_EXTENSIONS and serve them as plain text (e.g. text/plain or text/x-python) so “View source” opens the actual file.
Result: Citation links for code (e.g. MarginCall/tests/eval_llm.py) open the file in the existing doc viewer; later we can add “scroll to line” (e.g. hash or query param) if desired.
4. UI: render citations with links + code snippet
Where: ui/static/app.js (and optionally a small addition in index.html/style.css).
Current: Citations are rendered as “1. repo/path — heading” with a link that calls loadDoc(repo, path).
Change:
Keep that link for every citation.
If the citation has start_line and end_line (and optionally snippet):
Label: e.g. “repo/path (lines 10–25)”.
Below the link (or in an expandable block), render a &lt;pre&gt; with the snippet (or fetch snippet by repo/path/start/end if we move to a “snippet API” later).
If no line range, keep current behavior (doc link only).
Result: User sees “Answer …” and below “References” with links plus, for code refs, the relevant snippet so they don’t have to open the file to see the exact lines.
5. Prompting (optional but helpful)
Where: lib/ai_engine.py (system or user message for the RAG call).
Change: Add one line to the effect: “When citing code, mention file and line range; the system will attach the exact snippet in references.”
Result: Model tends to say things like “see tests/eval_llm.py (lines 10–25)” which matches the citation format we show.
Implementation order
Step	Task	Enables
1	Code chunker + store start_line/end_line in Chroma	Code in RAG context
2	Ingest: collect .py (and optionally others), chunk with code chunker, add to index	Retrieval of code for questions like “testing strategy for LLMs”
3	ai_engine: build citations with start_line/end_line and snippet (read from effective root)	API returns snippet for code refs
4	Doc viewer: allow .py (and chosen extensions)	“View source” opens the file
5	Frontend: render citation line range + &lt;pre&gt; snippet when present	User sees links and relevant code
Design choices to decide
Which code to index: Only .py, or also .yaml/.toml/.sh (e.g. for “how do we run tests”). Start with .py is simplest.
Snippet in backend vs API: Doing snippet in the backend (when building citations) keeps the frontend simple and reuses effective-root resolution. A separate GET /api/doc_snippet?repo=&path=&start=&end= is possible later for “load snippet on demand” or for line anchoring in the doc viewer.
Line numbers in doc viewer: Adding #L10 or ?line=10 to the doc URL and scrolling the viewer to that line is a follow-up; not required for “answer + links + relevant code in the citation block.”
This is the plan; we can implement it step by step (e.g. start with 1 + 2 so code is in the index and answers use it, then 3–5 so citations show links and snippets).
