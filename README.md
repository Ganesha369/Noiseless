# LeadSignal ⚡ | Multi-Agent B2B Opportunity Radar

**LeadSignal** is a production-grade multi-agent research tool built with **CrewAI**, **Groq**, and **Streamlit**. It mines high-signal B2B opportunities from 7 free public sources, filters out noise using LLM-backed buyer intent screening, enforces quality via a Watcher critic agent, and generates actionable Notion pages and outreach email drafts.

---

## 🏗️ Architecture & Multi-Agent Design

LeadSignal deploys **3 Main CrewAI Agents + 1 Quality Watcher/Critic Agent**:

1. **Lead Signal Scout Agent** (`ScoutAgent`):
   - Aggregates raw opportunities across 7 free public sources: HackerNews (Algolia API), GitHub public issues/repos, YC Startup dataset (`yc-oss`), Product Hunt RSS, Reddit public JSON, Dev.to articles, and Jobicy B2B remote jobs.
2. **Signal Noise Screener Agent** (`FilterAgent`):
   - Screens raw items for commercial intent, buyer urgency, and pain points. Batches LLM requests to optimize Groq rate limit usage.
3. **Lead Qualifier & Strategist Agent** (`QualifierAgent`):
   - Qualifies high-signal leads and drafts personalized, high-converting cold email outreach strategies with custom hooks and low-friction CTAs.
4. **Quality Watcher Critic Agent** (`WatcherAgent`):
   - Audits research output quality (0-100 score). If quality score < 70, triggers **EXACTLY ONE** automatic re-research loop with refined query parameters.
   - **Self-Correcting Guardrail**: Hard-capped in code (`max_retries = 1`) to guarantee no infinite loops or uncontrolled token consumption.

---

## 🛡️ Reliability & Fault-Tolerant System Design

- **Free Public Source Integration**: Operates without required paid keys. Uses public endpoints for HN, YC, Product Hunt, Reddit, Dev.to, Jobicy, and public GitHub search.
- **Reddit Rate-Limit Resilience**: Sends custom `User-Agent` headers. Isolates network failures cleanly so one blocked source won't crash the pipeline.
- **Automatic 1-Retry Backoff**: Every HTTP call incorporates 1 transient failure retry.
- **Groq API Efficiency**: Minimal token footprint through batched structured JSON prompt completions.
- **Human-In-The-Loop Safety**: No auto-sending. Email copying and Notion sync require explicit user approval.
- **Real-Time Observability**: Live "Connected Sources" sidebar panel and a visible "Reliability Log" panel displaying timestamped step execution traces.

---

## 🚀 Quickstart & Local Setup

### 1. Prerequisites
- Python 3.10+
- Groq API Key (`GROQ_API_KEY`)
- Notion Token (`NOTION_TOKEN`)
- GitHub Token (`GITHUB_TOKEN` - Optional)

### 2. Environment Setup
Clone the repository and install dependencies:
```bash
pip install -r requirements.txt
```

Create your `.env` file based on `.env.example`:
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
NOTION_TOKEN=ntn_your_notion_token_here
GITHUB_TOKEN=github_pat_your_github_token_here
```

### 3. Launch Application
Run the Streamlit application locally:
```bash
streamlit run app.py
```

Open browser at `http://localhost:8501`.

---

## 🧪 Verification & Testing

To verify fallback logic and network resilience:
1. Run a search query with an invalid/blocked key or disable a source in the sidebar.
2. Observe the **Reliability Log** panel: notice how the failed source updates to `FAILED` or `FALLBACK`, while the remaining 6 sources continue seamlessly to yield qualified leads.

---

*Reliability design inspired by agent-observability practices.*
