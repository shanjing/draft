1. Add X support — fetch and store X posts. [De-prioritized]
2. Accept browser plugin bookmark-style drops into the source box in the UI. [De-prioritized]
3. Encryption on vault-guarded files.[De-prioritized]. 
4. API encryption for MCP **(WIP:current focus)**
5. Expose the project as an MCP server for agents. **(WIP:current focus)**
6. In **setup.sh**: when the user skips AI (no API key), show "Draft still works well with index/search; only AI assistance is disabled." [DONE]
7. *** **setup.sh** should detect new vs existing install — new = all doc sources empty; existing = **~/.draft/.doc_sources** and vault already have files. [DONE]
8. *** **setup.sh** should check consistency between **sources.yaml**, **~/.draft/.doc_sources**, and vault. [DONE]

--- setup.sh / UX ---
9. *** **setup.sh** re-run: detect new vs existing install. For existing, show current state (sources, vault, LLM config, RAG index) and offer targeted prompts (add more? reconfigure LLM? rebuild RAG? start UI?) instead of full wizard. [DONE]
10. "Other" model: parse **provider:model** (e.g. **openai:gpt-4**) and call **setup_env_writer** with the correct mode (or add a custom/other mode). Fix confirmation text so it does not say "Ollama" when the user entered a non-Ollama string. [DONE]
11. **setup.sh**: rationalize **set -e** vs **|| true** — document which steps are must-fail vs best-effort; avoid **|| true** on the critical path (verify, add source, LLM write).[DONE]
12. RAG prompt: reword "RAG/index is required" so it is clear building now is optional (e.g. "Build RAG/index now? You can also do this later from the UI."). [DONE]
13. Write **.draft-ui.log** under **DRAFT_HOME** (**~/.draft**), not repo root; update serve/start path if needed. [DONE]
14. **setup.sh** non-interactive: add **--yes**, **--skip-sources**, **--no-llm**, **--no-rag**, **--no-start-ui** (and/or **DRAFT_SETUP_YES**). When non-TTY or **--yes**, use safe defaults and skip read prompts. [DONE]

1. **RAG Step 2 Plan: add codebase to the vector DB for semantic Q&A [DONE]**
