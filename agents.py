import os
import json
import time
import logging
from typing import Dict, List, Any, Tuple, Optional
from groq import Groq
from tools import (
    global_logger,
    fetch_hacker_news,
    fetch_github_issues,
    fetch_yc_companies,
    fetch_product_hunt_rss,
    fetch_reddit_public,
    fetch_dev_to,
    fetch_jobicy_jobs,
)

logger = logging.getLogger("LeadSignal.Agents")

class GroqLLMManager:
    """Singleton helper for executing batch LLM tasks via Groq with rate-limit retries."""
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.client = None
        if self.api_key and not self.api_key.startswith("gsk_your"):
            try:
                self.client = Groq(api_key=self.api_key)
            except Exception as e:
                global_logger.log("LLM", f"Error initializing Groq client: {str(e)}", "ERROR")

    def call_llm(self, system_prompt: str, user_prompt: str, model: str = "groq/compound-mini", temperature: float = 0.2) -> Optional[str]:
        if not self.client:
            global_logger.log("LLM", "No valid Groq API client initialized. Falling back to rule-based fallback processing.", "WARNING")
            return None
        
        models_to_try = [model, "groq/compound", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]
        
        for mdl in models_to_try:
            for attempt in range(1, 2):  # Try model
                try:
                    global_logger.log("LLM", f"Calling Groq LLM ({mdl}) - Attempt {attempt}")
                    start_t = time.time()
                    response = self.client.chat.completions.create(
                        model=mdl,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=temperature,
                        max_tokens=2000
                    )
                    dur = int((time.time() - start_t) * 1000)
                    global_logger.log("LLM", f"Groq LLM response received from {mdl} in {dur}ms", "SUCCESS")
                    return response.choices[0].message.content
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "rate_limit" in err_str:
                        global_logger.log("LLM", f"Groq rate limit hit for {mdl}. Pausing 2s before retry...", "RETRY")
                        time.sleep(2)
                    else:
                        global_logger.log("LLM", f"Groq API model {mdl} note: {err_str}", "WARNING")
                        break  # Try next model in list
        return None

def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Safely extract JSON dictionary from LLM response text."""
    if not text:
        return None
    cleaned = text.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json")[1].split("```")[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(cleaned)
    except Exception:
        # Fallback regex search for json object
        import re
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None

llm_manager = GroqLLMManager()

# ==================== CREWAI AGENT SPECIFICATIONS ====================

class ScoutAgent:
    """Agent 1: Lead Signal Scout / Researcher"""
    def __init__(self):
        self.role = "Lead Signal Scout"
        self.goal = "Search free public sources to harvest B2B opportunities and buyer intent posts."

    def execute(self, query: str, sources_config: Dict[str, bool]) -> List[Dict[str, Any]]:
        global_logger.log("ScoutAgent", f"Scout Agent searching across public data channels for: '{query}'")
        raw_leads = []

        if sources_config.get("HackerNews", True):
            raw_leads.extend(fetch_hacker_news(query))
        if sources_config.get("GitHub", True):
            raw_leads.extend(fetch_github_issues(query))
        if sources_config.get("YC_OSS", True):
            raw_leads.extend(fetch_yc_companies(query))
        if sources_config.get("ProductHunt", True):
            raw_leads.extend(fetch_product_hunt_rss(query))
        if sources_config.get("Reddit", True):
            raw_leads.extend(fetch_reddit_public(query))
        if sources_config.get("DevTo", True):
            raw_leads.extend(fetch_dev_to(query))
        if sources_config.get("Jobicy", True):
            raw_leads.extend(fetch_jobicy_jobs(query))

        global_logger.log("ScoutAgent", f"Scout Agent collected {len(raw_leads)} total raw potential signals.", "SUCCESS")
        return raw_leads


class FilterAgent:
    """Agent 2: Signal vs Noise Screener"""
    def __init__(self):
        self.role = "Signal Noise Screener"
        self.goal = "Filter noise, score buyer intent, and extract high-signal B2B leads."

    def execute(self, raw_leads: List[Dict[str, Any]], niche: str) -> List[Dict[str, Any]]:
        global_logger.log("FilterAgent", f"Filter Agent screening {len(raw_leads)} raw items for niche: '{niche}'")
        if not raw_leads:
            return []

        # Prepare batch payload for single Groq call to preserve rate limits
        compact_candidates = [
            {
                "idx": i,
                "source": item.get("source"),
                "title": item.get("title"),
                "snippet": item.get("snippet", "")[:200],
                "author": item.get("author")
            }
            for i, item in enumerate(raw_leads[:18])  # cap at top candidates
        ]

        system_prompt = (
            "You are an expert B2B Lead Screener. Analyze candidate posts/launches/issues for genuine commercial intent.\n"
            "Identify leads where a founder, business, or team needs services, software, design, development, or consulting.\n"
            "Return a JSON object with key 'filtered_leads': a list of objects containing:\n"
            "- idx: integer matching candidate index\n"
            "- relevance_score: integer 0-100 (high if real buying intent or startup need)\n"
            "- intent_signal: string brief explanation of why this is a good opportunity\n"
            "- pain_point: string key problem or demand identified\n"
            "- decision_maker: string inferred buyer persona (e.g., CTO, Founder, Product Lead)\n"
            "Only return leads with relevance_score >= 60."
        )

        user_prompt = f"Target Niche/Service: {niche}\nCandidates JSON:\n{json.dumps(compact_candidates, indent=2)}"

        llm_resp = llm_manager.call_llm(system_prompt, user_prompt)
        filtered_results = []

        if llm_resp:
            parsed = extract_json(llm_resp)
            if parsed:
                try:
                    lead_evals = parsed.get("filtered_leads", [])
                    eval_map = {item.get("idx"): item for item in lead_evals if isinstance(item, dict)}

                    for i, item in enumerate(raw_leads[:18]):
                        if i in eval_map:
                            ev = eval_map[i]
                            item_copy = dict(item)
                            item_copy["relevance_score"] = int(ev.get("relevance_score", 75))
                            item_copy["intent_signal"] = ev.get("intent_signal", "Strong B2B buying signal")
                            item_copy["pain_point"] = ev.get("pain_point", "Needs specialized technical / growth support")
                            item_copy["decision_maker"] = ev.get("decision_maker", "Founder / Business Owner")
                            item_copy["niche"] = niche
                            filtered_results.append(item_copy)
                except Exception as e:
                    global_logger.log("FilterAgent", f"Error processing LLM response: {str(e)}. Using fallback scoring.", "WARNING")

        # Fallback if LLM unavailable or returned empty
        if not filtered_results:
            global_logger.log("FilterAgent", "Applying rule-based heuristic filtering fallback.", "INFO")
            for item in raw_leads:
                title_lower = item.get("title", "").lower()
                snippet_lower = item.get("snippet", "").lower()
                
                score = 70
                if any(k in title_lower or k in snippet_lower for k in ["hiring", "need", "looking for", "agency", "dev", "design", "build", "tool"]):
                    score += 15
                if item.get("source") in ["YC_OSS", "Jobicy"]:
                    score += 10
                    
                item_copy = dict(item)
                item_copy["relevance_score"] = min(score, 98)
                item_copy["intent_signal"] = f"Opportunity detected in {item.get('source')} related to {niche}"
                item_copy["pain_point"] = f"Active project, launch or hiring need matching '{niche}' keywords."
                item_copy["decision_maker"] = "Founder / Hiring Manager"
                item_copy["niche"] = niche
                filtered_results.append(item_copy)

        # Sort descending by relevance score
        filtered_results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        global_logger.log("FilterAgent", f"Filter Agent identified {len(filtered_results)} high-signal qualified leads.", "SUCCESS")
        return filtered_results[:8]


class QualifierAgent:
    """Agent 3: Lead Qualifier & Email Outreach Drafter"""
    def __init__(self):
        self.role = "Lead Qualifier & Strategist"
        self.goal = "Qualify B2B leads and draft personalized, high-converting outreach email templates."

    def execute(self, filtered_leads: List[Dict[str, Any]], niche: str) -> List[Dict[str, Any]]:
        global_logger.log("QualifierAgent", f"Qualifier Agent drafting custom outreach strategies for top {len(filtered_leads)} leads.")
        if not filtered_leads:
            return []

        leads_to_process = filtered_leads[:5]
        
        system_prompt = (
            "You are a top B2B Sales Strategist & Copywriter. Create personalized, non-spammy outreach email drafts.\n"
            "For each lead, craft a tailored email draft following this structure:\n"
            "- Subject line: Catchy, specific, short (3-6 words)\n"
            "- Hook: Compliment or mention their specific post/project\n"
            "- Value Prop: Concise explanation of how we help with their specific pain point\n"
            "- Call to Action (CTA): Soft, low-friction request (e.g., 'open to a 5-min async demo?')"
            "Return a JSON object with key 'qualified_leads': list of objects containing:\n"
            "- idx: integer matching lead index\n"
            "- email_subject: string\n"
            "- email_body: string full professional email text\n"
            "- recommended_offer: string recommended service/product angle"
        )

        compact_payload = [
            {
                "idx": i,
                "title": lead.get("title"),
                "source": lead.get("source"),
                "author": lead.get("author"),
                "pain_point": lead.get("pain_point")
            }
            for i, lead in enumerate(leads_to_process)
        ]

        user_prompt = f"Our Niche/Service Offer: {niche}\nLeads JSON:\n{json.dumps(compact_payload, indent=2)}"

        llm_resp = llm_manager.call_llm(system_prompt, user_prompt)
        qualified = []

        if llm_resp:
            parsed = extract_json(llm_resp)
            if parsed:
                try:
                    email_evals = parsed.get("qualified_leads", [])
                    eval_map = {item.get("idx"): item for item in email_evals if isinstance(item, dict)}

                    for i, lead in enumerate(leads_to_process):
                        lead_copy = dict(lead)
                        if i in eval_map:
                            ev = eval_map[i]
                            lead_copy["email_subject"] = ev.get("email_subject", f"Quick question re: {lead.get('title')[:30]}")
                            lead_copy["email_body"] = ev.get("email_body", self._generate_fallback_email(lead, niche))
                            lead_copy["recommended_offer"] = ev.get("recommended_offer", f"{niche} Custom Solution")
                        else:
                            lead_copy["email_subject"] = f"Quick thought on {lead.get('title')[:30]}"
                            lead_copy["email_body"] = self._generate_fallback_email(lead, niche)
                            lead_copy["recommended_offer"] = f"{niche} Specialized Consulting"
                        qualified.append(lead_copy)
                except Exception as e:
                    global_logger.log("QualifierAgent", f"Error processing email response: {str(e)}. Using fallback generator.", "WARNING")

        if not qualified:
            for lead in leads_to_process:
                lead_copy = dict(lead)
                lead_copy["email_subject"] = f"Quick question regarding {lead.get('title')[:30]}"
                lead_copy["email_body"] = self._generate_fallback_email(lead, niche)
                lead_copy["recommended_offer"] = f"{niche} Advisory & Development"
                qualified.append(lead_copy)

        global_logger.log("QualifierAgent", f"Qualifier Agent successfully generated {len(qualified)} personalized outreach strategies.", "SUCCESS")
        return qualified

    def _generate_fallback_email(self, lead: Dict[str, Any], niche: str) -> str:
        author = lead.get("author", "Founder")
        title = lead.get("title", "your project")
        source = lead.get("source", "public discussion")
        return (
            f"Hi {author},\n\n"
            f"I came across your post regarding '{title}' on {source} and noticed your team's focus on solving {lead.get('pain_point', niche)}.\n\n"
            f"We specialize in helping founders and teams in the {niche} space rapidly deploy high-signal solutions without adding tech debt or overhead.\n\n"
            f"Would you be open to a quick 5-minute chat or an async review of how we could solve this for you?\n\n"
            f"Best regards,\n[Your Name]\n[Your Company / Agency]"
        )


class WatcherAgent:
    """Agent 4: Quality Watcher & Re-Research Critic Guardrail"""
    def __init__(self):
        self.role = "Quality Watcher & Critic"
        self.goal = "Evaluate research quality score and enforce a hard-capped max 1 retry loop."

    def evaluate(self, qualified_leads: List[Dict[str, Any]], niche: str, is_retry_run: bool) -> Tuple[int, str, bool]:
        global_logger.log("WatcherAgent", f"Watcher Agent auditing research output quality (Is retry loop: {is_retry_run}).")
        
        if not qualified_leads:
            score = 30
            rationale = "Zero qualified leads generated."
            global_logger.record_watcher_audit(niche, score, rationale, passed=False, is_retry=is_retry_run)
            return score, rationale, False

        avg_relevance = sum(l.get("relevance_score", 70) for l in qualified_leads) / len(qualified_leads)
        has_emails = all(len(l.get("email_body", "")) > 50 for l in qualified_leads)
        
        # Calculate base quality score
        score = int(avg_relevance)
        if len(qualified_leads) >= 3:
            score = min(score + 10, 98)
        if not has_emails:
            score -= 20

        passed = score >= 70
        rationale = f"Audited {len(qualified_leads)} leads with avg relevance {avg_relevance:.1f}/100. Outreach quality check: {'PASSED' if has_emails else 'DEGRADED'}."
        
        global_logger.record_watcher_audit(niche, score, rationale, passed=passed, is_retry=is_retry_run)
        return score, rationale, passed


# ==================== MAIN PIPELINE ORCHESTRATOR ====================

def run_leadsignal_pipeline(niche_query: str, sources_config: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    """
    Executes the complete 4-agent LeadSignal pipeline.
    Enforces a strict HARD-CAPPED max 1 automatic re-research loop if quality score < 70.
    """
    if not sources_config:
        sources_config = {
            "HackerNews": True, "GitHub": True, "YC_OSS": True,
            "ProductHunt": True, "Reddit": True, "DevTo": True, "Jobicy": True
        }

    global_logger.log("Pipeline", f"=== STARTING LEADSIGNAL AGENT PIPELINE FOR: '{niche_query}' ===")
    
    scout = ScoutAgent()
    filter_agent = FilterAgent()
    qualifier = QualifierAgent()
    watcher = WatcherAgent()

    # STEP 1: First Pass Execution
    global_logger.log("Pipeline", "--- Stage 1: Scout Agent Research ---")
    raw_items = scout.execute(niche_query, sources_config)

    global_logger.log("Pipeline", "--- Stage 2: Filter Agent Noise Reduction ---")
    filtered_items = filter_agent.execute(raw_items, niche_query)

    global_logger.log("Pipeline", "--- Stage 3: Qualifier Agent Strategy & Email Drafting ---")
    qualified_leads = qualifier.execute(filtered_items, niche_query)

    global_logger.log("Pipeline", "--- Stage 4: Watcher Agent Quality Audit ---")
    score, rationale, passed = watcher.evaluate(qualified_leads, niche_query, is_retry_run=False)

    triggered_re_research = False
    re_research_query = ""

    # SELF-CORRECTING LOOP GUARDRAIL: Hard-capped at exactly ONE retry!
    if not passed and score < 70:
        triggered_re_research = True
        re_research_query = f"{niche_query} hiring agency contract looking for"
        global_logger.log(
            "SelfCorrectionLoop",
            f"Quality Score {score}/100 below threshold (70). Triggering EXACTLY ONE automatic re-research with refined query: '{re_research_query}'",
            "WARNING"
        )
        
        # Re-run Scout, Filter, Qualifier with refined query
        retry_raw = scout.execute(re_research_query, sources_config)
        retry_filtered = filter_agent.execute(retry_raw, re_research_query)
        retry_qualified = qualifier.execute(retry_filtered, niche_query)

        # Final audit (will not trigger another retry regardless of score)
        score_final, rationale_final, passed_final = watcher.evaluate(retry_qualified, re_research_query, is_retry_run=True)
        
        global_logger.log("SelfCorrectionLoop", f"Re-research completed. Final Quality Score: {score_final}/100. Hard-cap reached (1/1 retries max).", "INFO")
        
        qualified_leads = retry_qualified
        score = score_final
        rationale = f"[Post Re-Research] {rationale_final}"

    global_logger.log("Pipeline", f"=== PIPELINE COMPLETED SUCCESSFULLY WITH {len(qualified_leads)} LEADS ===", "SUCCESS")

    return {
        "niche_query": niche_query,
        "qualified_leads": qualified_leads,
        "quality_score": score,
        "quality_rationale": rationale,
        "triggered_re_research": triggered_re_research,
        "re_research_query": re_research_query,
        "logs": global_logger.get_logs(),
        "source_status": global_logger.get_source_status(),
        "watcher_history": global_logger.watcher_scores
    }
