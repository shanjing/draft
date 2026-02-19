## MarginCall

A stock analyst agent.

**Requirements to run the agent**

1. Must be in the virtual environment (`cd adk-lab; source .venv/bin/activate`)
2. Must have a valid `GOOGLE_API_KEY` defined in the repo root `adk-lab/.env` file.  
   (To create your Google API key, go to [Google AI Studio](https://aistudio.google.com/api-keys).)

The current WIP only supports Google Gemini models and local LLM models that support tools (e.g., Qwen).

**To start the agent**

```
adk web
# 1. Open browser to localhost:8000
# 2. On the left side of the screen, select "stock_analyst"
# 3. In the chat box, start talking to the agent

# To run in CLI for debugging or text-based chat:
python -m main run --help
python -m main run -i "tell me about GOOGL"
python -m main run -i "tell me about GOOGL" -d -t
```

**Troubleshooting**

1. Make sure you have created and activated the virtual environment; see the repo root's README.md.
2. Make sure you have a valid `GOOGLE_API_KEY` defined in `adk-lab/.env`.
3. Make sure you have a valid model defined in the `.env` file.


**Agentic Pattern**

Supervisor → AgentTool(sequential pipeline (data → report → present)):


```
    ┌─────────────────────────────────────────────────────────┐
    │ stock_analyst (root)                                    │
    │ tools: stock_analysis_pipeline, invalidate_cache         │
    └───────────────────────────┬─────────────────────────────┘
                                │
                                v
    ┌─────────────────────────────────────────────────────────┐
    │ stock_analysis_pipeline (sequential)                    │
    └───────────────────────────┬─────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        v                       v                       v
    ┌───────────────┐     ┌───────────────┐     ┌──────────────┐
    │stock_data_    │ ──> │report_        │ ──> │ presenter    │
    │collector      │     │synthesizer    │     │ (no tools)   │
    │               │     │ (no tools)    │     └──────────────┘
    │ tools:        │     │               │
    │ fetch_stock_  │     └───────────────┘
    │ price,        │
    │ fetch_        │
    │ financials,   │
    │ fetch_        │
    │ technicals_   │
    │ with_chart,   │
    │ fetch_cnn_    │
    │ greedy,       │
    │ fetch_vix,    │
    │ fetch_        │
    │ stocktwits_   │
    │ sentiment,    │
    │ fetch_        │
    │ options_      │
    │ analysis,     │
    │ news_fetcher  │
    └───────┬───────┘
            │
            v
    ┌───────────────┐
    │ news_fetcher  │
    │ google_search │
    │ | brave_search│
    └───────────────┘
```

