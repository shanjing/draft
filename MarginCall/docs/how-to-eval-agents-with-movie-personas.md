# How to Run Evals When an Agent Has a Movie Persona

**Why the evaluation response_match_score and strict tool args failed the AI agent, and how it was fixed with rubrics and prompt tweaks.**

---

## The Problem

MarginCall's root agent is instructed to respond in the style of **Sam Rogers** (the main role in the movie *Margin Call*): sharp, conversational, and a bit cynical. For stock research it runs a pipeline and returns a full report. For general questions like "What do you think about the market?" it answers in character with no tools.

Google ADK evals were added: `tool_trajectory_avg_score` (right tools called?) and `response_match_score` (reply match a reference?). The tests kept failing. Not because the agent was wrong, but because the metrics assumed deterministic and literal outputs.

---

## Root Cause 1: Token Overlap Is Not Fair to Personas

Reading ADK's documentation, it turns out **response_match_score** in ADK is reference-based. It compares the model's reply to an expected string with token-level overlap (e.g. ROUGE). If the reference says "The market, huh? It's a complicated mechanism…" and the model says "The market's a fickle beast, full of potential and peril…", the overlap is low. Even though both answers are on-topic and in character.

After loosening the threshold and rewriting the expected text to be "semantic" (e.g. a short description of what a good answer should contain), the scores stayed low. The underlying issue was: any metric that rewards exact word similarity punishes variations such as persona. So the evals were effectively testing "did the model repeat this sentence?" instead of "did the model give a good answer?"

---

## Root Cause 2: Non-Deterministic Tool Arguments

For queries like "Tell me about AAPL" the agent is expected to call `stock_analysis_pipeline` with `request: "AAPL"`. Sometimes it did. Sometimes it sent `request: "Tell me about AAPL"` (the full user message). The tool trajectory evaluator does strict arg matching. So the latter case scored 0.0 even though the right tool was invoked and the pipeline behaved correctly.

There were two separate issues: (1) response quality judged by tokens, (2) tool-call quality judged by exact args.

---

## Fix 1: Swap to Rubric-Based Response Quality

`response_match_score` was replaced with **rubric_based_final_response_quality_v1**. That metric uses an LLM-as-judge. It evaluates the reply against configurable rubrics, not against a single reference string.

In `evals/test_config.json` three rubrics are used:

- **Relevance** — The response addresses the user's query or ticker.
- **Completeness** — The response is substantive (data, analysis, or opinion), not empty or evasive.
- **Persona** — The response does not sound like a generic corporate chatbot. Some personality is evident, or the brevity fits the question.

The judge can mark "Tell me about AAPL" as relevant and complete even when the wording changes every run. For "What do you think about the market?" it can accept different Sam Rogers phrasings as long as they are on-topic and in character. In practice the judge reasons that the agent delivers a structured and factual report for research and conveys a professional and analytical tone consistent with the agent's role. So persona and correctness are both rewarded instead of penalized.

The rubric threshold is set to **0.6** (e.g. 2 of 3 rubrics passing). So that brief factual answers (e.g. earnings date) or short opinion answers (e.g. market chat) do not fail when one rubric is borderline.

---

## Fix 2: Instruct the Agent to Pass Only the Ticker

To keep tool-arg checks meaningful, stable args are needed so the eval can assert them. The root agent instruction was changed in `stock_analyst/prompts.py`:

- **Before:** "Call the 'stock_analysis_pipeline' tool with their request."
- **After:** "Extract only the ticker symbol (e.g. 'AAPL') and pass it as the request argument to the 'stock_analysis_pipeline' tool. Do not include conversational filler in the tool arguments."

That makes the agent's contract explicit. For pipeline (and refresh) flows, the tool gets the ticker, not the raw user sentence. Evals can then expect `request: "AAPL"` and get it consistently.

---

## Fix 3: Rubric Wording for Mixed Content

For the **completeness** rubric both long reports and short answers must be allowed. The rubric text is: *"The response provides a meaningful reply — whether data, analysis, opinion, or conversational engagement — rather than refusing or giving an empty answer."* That way "Financials for NVDA" can be a one-paragraph summary and "What do you think about the market?" can be a few lines of opinion. Both count as complete.

For **persona** the rubric avoids requiring Sam Rogers flair on every reply. It says: *"The response does not sound like a generic corporate chatbot. Some personality is evident, or the brevity itself is natural for the question asked."* So a terse earnings date is fine. A long report can be professional and analytical rather than overtly in-character, and still pass.

---

## What Appears in the Logs

When evals run with `print_detailed_results=True`, the rubric judge outputs **Property**, **Evidence**, **Rationale**, and **Verdict** per rubric. For example, for "Tell me about AAPL" the judge cites the final answer's content (price, technicals, financials, sentiment, earnings date, rating, Reddit). It explains that the answer directly addresses the user's query about AAPL and marks relevance and completeness as *yes*. For persona it notes that the instructions distinguish general questions (Sam Rogers style) from stock research (pipeline). The delivered report is appropriate for a senior stock data research analyst and consistent with the agent's role. So the verdict is *yes* even when the reply is not literally in character. These snippets can be used to tune rubrics or thresholds without pasting full responses into the doc.

---

## Summary

| Issue | Root cause | Fix |
|-------|------------|-----|
| Low response_match_score | Token-overlap metric penalizes persona-driven wording | Use rubric_based_final_response_quality_v1 with relevance, completeness, and persona rubrics |
| Low tool_trajectory_avg_score | Agent sometimes passed full user text as request instead of ticker | Add explicit instruction: "Extract only the ticker symbol… Do not include conversational filler" |
| Rubric too strict on short answers | Single bar for completeness and persona | Word rubrics to accept opinions, brief factual answers, and natural brevity; set threshold to 0.6 |

Eval layout and commands are unchanged: `evals/*.test.json`, `evals/test_config.json`, and `pytest tests/test_agent_evals.py -v -s`. See **docs/AIEvalsPlan.md** and **docs/TestingStrategy.md** for the full eval plan and test layers.
