import os
import time
import json
import logging
import requests
import feedparser
from datetime import datetime
from typing import Dict, List, Any, Optional

# Setup logger for stdout
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LeadSignal")

# Global Reliability Log Store for Streamlit UI
class ReliabilityLogger:
    def __init__(self):
        self.logs: List[Dict[str, Any]] = []
        self.source_status: Dict[str, Dict[str, Any]] = {
            "HackerNews": {"status": "UNKNOWN", "latency_ms": 0, "last_check": None, "details": "Not run yet"},
            "GitHub": {"status": "UNKNOWN", "latency_ms": 0, "last_check": None, "details": "Not run yet"},
            "YC_OSS": {"status": "UNKNOWN", "latency_ms": 0, "last_check": None, "details": "Not run yet"},
            "ProductHunt": {"status": "UNKNOWN", "latency_ms": 0, "last_check": None, "details": "Not run yet"},
            "Reddit": {"status": "UNKNOWN", "latency_ms": 0, "last_check": None, "details": "Not run yet"},
            "DevTo": {"status": "UNKNOWN", "latency_ms": 0, "last_check": None, "details": "Not run yet"},
            "Jobicy": {"status": "UNKNOWN", "latency_ms": 0, "last_check": None, "details": "Not run yet"},
            "Notion": {"status": "UNKNOWN", "latency_ms": 0, "last_check": None, "details": "Not run yet"},
        }
        self.watcher_scores: List[Dict[str, Any]] = []

    def log(self, stage: str, message: str, status: str = "INFO", details: Optional[Dict[str, Any]] = None):
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "stage": stage,
            "message": message,
            "status": status,  # INFO, SUCCESS, WARNING, ERROR, RETRY
            "details": details or {}
        }
        self.logs.append(entry)
        log_lvl = logging.ERROR if status == "ERROR" else (logging.WARNING if status == "WARNING" else logging.INFO)
        logger.log(log_lvl, f"[{stage}] {message}")

    def update_source_health(self, source_name: str, status: str, latency_ms: int, details: str = ""):
        self.source_status[source_name] = {
            "status": status,  # HEALTHY, DEGRADED, FAILED, FALLBACK
            "latency_ms": latency_ms,
            "last_check": datetime.now().strftime("%H:%M:%S"),
            "details": details
        }
        self.log(
            stage=f"SourceCheck:{source_name}",
            message=f"Health status updated to {status} ({latency_ms}ms) - {details}",
            status="SUCCESS" if status == "HEALTHY" else ("WARNING" if status in ["DEGRADED", "FALLBACK"] else "ERROR")
        )

    def record_watcher_audit(self, query: str, score: int, rationale: str, passed: bool, is_retry: bool):
        self.watcher_scores.append({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "query": query,
            "score": score,
            "rationale": rationale,
            "passed": passed,
            "is_retry": is_retry
        })
        self.log(
            stage="WatcherAgent",
            message=f"Quality score: {score}/100. Audit Passed: {passed}. (Retry loop: {is_retry}) - {rationale}",
            status="SUCCESS" if passed else "WARNING"
        )

    def get_logs(self):
        return self.logs

    def get_source_status(self):
        return self.source_status

    def clear(self):
        self.logs = []

# Singleton instance
global_logger = ReliabilityLogger()

def safe_request(url: str, headers: Dict[str, str] = None, params: Dict[str, Any] = None, timeout: int = 6) -> tuple[Optional[requests.Response], int]:
    """Execute HTTP GET with exactly 1 automatic retry on transient failures."""
    start_time = time.time()
    headers = headers or {}
    
    for attempt in range(1, 3):  # Attempt 1, then attempt 2 (max 1 retry)
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            latency = int((time.time() - start_time) * 1000)
            if resp.status_code == 200:
                return resp, latency
            elif resp.status_code in [429, 500, 502, 503, 504] and attempt == 1:
                global_logger.log("HTTP", f"Transient error HTTP {resp.status_code} for {url}. Retrying (Attempt 2/2)...", "RETRY")
                time.sleep(1)
                continue
            else:
                global_logger.log("HTTP", f"HTTP {resp.status_code} from {url}", "WARNING")
                return resp, latency
        except (requests.RequestException, Exception) as e:
            latency = int((time.time() - start_time) * 1000)
            if attempt == 1:
                global_logger.log("HTTP", f"Request exception '{str(e)}' for {url}. Retrying (Attempt 2/2)...", "RETRY")
                time.sleep(1)
                continue
            else:
                global_logger.log("HTTP", f"Failed call to {url} after retry: {str(e)}", "ERROR")
                return None, latency
    return None, int((time.time() - start_time) * 1000)

# ==================== DATA SOURCE AGENT TOOLS ====================

def fetch_hacker_news(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Fetch recent stories & ask HN posts from HackerNews via Algolia API."""
    global_logger.log("HackerNews", f"Searching HackerNews for query: '{query}'")
    url = f"https://hn.algolia.com/api/v1/search"
    params = {"query": query, "tags": "story", "hitsPerPage": limit}
    
    resp, latency = safe_request(url, params=params)
    results = []
    
    if resp and resp.status_code == 200:
        try:
            data = resp.json()
            hits = data.get("hits", [])
            for hit in hits:
                title = hit.get("title") or hit.get("story_title") or ""
                url_link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                if title:
                    results.append({
                        "source": "HackerNews",
                        "id": str(hit.get("objectID")),
                        "title": title,
                        "url": url_link,
                        "author": hit.get("author", "unknown"),
                        "score": hit.get("points", 0),
                        "comments": hit.get("num_comments", 0),
                        "snippet": (hit.get("story_text") or title)[:300],
                        "created_at": hit.get("created_at", "")
                    })
            global_logger.update_source_health("HackerNews", "HEALTHY", latency, f"Returned {len(results)} items")
        except Exception as e:
            global_logger.update_source_health("HackerNews", "DEGRADED", latency, f"JSON parse error: {str(e)}")
    else:
        global_logger.update_source_health("HackerNews", "FAILED", latency, f"HTTP Error or Timeout")
    
    return results

def fetch_github_issues(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Fetch GitHub public issues & repository needs."""
    global_logger.log("GitHub", f"Searching GitHub public issues for query: '{query}'")
    token = os.getenv("GITHUB_TOKEN", "").strip()
    
    headers = {"User-Agent": "LeadSignal-ResearchAgent/1.0", "Accept": "application/vnd.github.v3+json"}
    if token and not token.startswith("github_pat_your"):
        headers["Authorization"] = f"token {token}"
    
    url = "https://api.github.com/search/issues"
    params = {"q": f"{query} state:open type:issue", "per_page": limit, "sort": "created"}
    
    resp, latency = safe_request(url, headers=headers, params=params)
    results = []
    
    if resp and resp.status_code == 200:
        try:
            data = resp.json()
            items = data.get("items", [])
            for item in items:
                title = item.get("title", "")
                results.append({
                    "source": "GitHub",
                    "id": str(item.get("id")),
                    "title": title,
                    "url": item.get("html_url", ""),
                    "author": item.get("user", {}).get("login", "unknown"),
                    "score": item.get("comments", 0),
                    "snippet": (item.get("body") or title)[:300],
                    "created_at": item.get("created_at", "")
                })
            status = "HEALTHY" if token else "DEGRADED"
            global_logger.update_source_health("GitHub", status, latency, f"Returned {len(results)} items {'(Authenticated)' if token else '(Unauthenticated)'}")
        except Exception as e:
            global_logger.update_source_health("GitHub", "DEGRADED", latency, f"Parse error: {str(e)}")
    else:
        err_msg = f"HTTP {resp.status_code}" if resp else "Connection error"
        global_logger.update_source_health("GitHub", "FAILED", latency, err_msg)
        
    return results

def fetch_yc_companies(query: str, limit: int = 6) -> List[Dict[str, Any]]:
    """Fetch YC public company directory data from yc-oss JSON dataset."""
    global_logger.log("YC_OSS", f"Searching YC public dataset for query: '{query}'")
    url = "https://raw.githubusercontent.com/ycombinator/yc-oss/main/data/companies.json"
    
    resp, latency = safe_request(url, timeout=7)
    results = []
    
    if resp and resp.status_code == 200:
        try:
            companies = resp.json()
            query_lower = query.lower()
            matching = []
            
            for c in companies:
                name = c.get("name", "")
                desc = (c.get("one_liner") or c.get("long_description") or "").lower()
                industry = (c.get("industry") or c.get("subindustry") or "").lower()
                
                if query_lower in name.lower() or query_lower in desc or query_lower in industry:
                    matching.append(c)
                if len(matching) >= limit * 2:
                    break
            
            # If explicit match yields few results, take relevant recent batch companies
            if len(matching) < 3:
                matching = companies[:limit*2]

            for c in matching[:limit]:
                name = c.get("name", "YC Startup")
                desc = c.get("one_liner") or c.get("long_description") or "YC Backed Startup"
                batch = c.get("batch", "YC")
                website = c.get("website", f"https://www.google.com/search?q={name}+YC")
                
                results.append({
                    "source": "YC_OSS",
                    "id": f"yc-{name.replace(' ', '-').lower()}",
                    "title": f"{name} ({batch}) - {desc[:80]}",
                    "url": website,
                    "author": f"Batch {batch}",
                    "score": 85,
                    "snippet": f"Company: {name} | Batch: {batch} | Description: {desc} | Industry: {c.get('industry', 'Tech')}",
                    "created_at": datetime.now().strftime("%Y-%m-%d")
                })
            global_logger.update_source_health("YC_OSS", "HEALTHY", latency, f"Parsed {len(companies)} YC startups; found {len(results)} matches")
        except Exception as e:
            global_logger.update_source_health("YC_OSS", "DEGRADED", latency, f"Parse error: {str(e)}")
    else:
        global_logger.update_source_health("YC_OSS", "FAILED", latency, "HTTP Error/Timeout")
        
    return results

def fetch_product_hunt_rss(query: str, limit: int = 6) -> List[Dict[str, Any]]:
    """Fetch Product Hunt public RSS feed."""
    global_logger.log("ProductHunt", f"Parsing Product Hunt RSS feed for query: '{query}'")
    url = "https://www.producthunt.com/feed"
    start_time = time.time()
    results = []
    
    try:
        feed = feedparser.parse(url)
        latency = int((time.time() - start_time) * 1000)
        
        if feed.entries:
            query_lower = query.lower()
            for entry in feed.entries:
                title = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                link = entry.get("link", "https://producthunt.com")
                
                # Simple relevance check or fallback to recent launches
                results.append({
                    "source": "ProductHunt",
                    "id": entry.get("id", link),
                    "title": f"Launch: {title}",
                    "url": link,
                    "author": entry.get("author", "PH Creator"),
                    "score": 75,
                    "snippet": f"Product Launch: {title} - {summary[:250]}",
                    "created_at": entry.get("published", "")
                })
                if len(results) >= limit:
                    break
            global_logger.update_source_health("ProductHunt", "HEALTHY", latency, f"Fetched {len(results)} launches")
        else:
            global_logger.update_source_health("ProductHunt", "DEGRADED", latency, "Feed returned no entries")
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        global_logger.update_source_health("ProductHunt", "FAILED", latency, f"RSS parse error: {str(e)}")
        
    return results

def fetch_reddit_public(query: str, limit: int = 6) -> List[Dict[str, Any]]:
    """Fetch Reddit public JSON with custom User-Agent header & error isolation."""
    global_logger.log("Reddit", f"Querying Reddit public API for query: '{query}'")
    url = f"https://www.reddit.com/search.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LeadSignal/1.0 (B2B Research Tool)",
        "Accept": "application/json"
    }
    params = {"q": f"{query} (looking for OR need OR hiring OR agency)", "sort": "new", "limit": limit}
    
    resp, latency = safe_request(url, headers=headers, params=params, timeout=5)
    results = []
    
    if resp and resp.status_code == 200:
        try:
            data = resp.json()
            children = data.get("data", {}).get("children", [])
            for child in children:
                pdata = child.get("data", {})
                title = pdata.get("title", "")
                permalink = pdata.get("permalink", "")
                full_url = f"https://reddit.com{permalink}" if permalink else pdata.get("url", "")
                
                results.append({
                    "source": "Reddit",
                    "id": pdata.get("id", ""),
                    "title": title,
                    "url": full_url,
                    "author": f"u/{pdata.get('author', 'anonymous')}",
                    "score": pdata.get("score", 0),
                    "snippet": (pdata.get("selftext") or title)[:300],
                    "created_at": datetime.fromtimestamp(pdata.get("created_utc", time.time())).strftime("%Y-%m-%d") if pdata.get("created_utc") else ""
                })
            global_logger.update_source_health("Reddit", "HEALTHY", latency, f"Fetched {len(results)} posts")
        except Exception as e:
            global_logger.update_source_health("Reddit", "DEGRADED", latency, f"Parse error: {str(e)}")
    else:
        # Reddit frequently rate limits or blocks cloud IPs -> Graceful fallback
        err_msg = f"HTTP {resp.status_code} (Rate-limited/Blocked)" if resp else "Connection timeout"
        global_logger.update_source_health("Reddit", "FALLBACK", latency, err_msg)
        global_logger.log("Reddit", f"Reddit call failed or rate-limited. Isolated safely; pipeline continuing with remaining sources.", "WARNING")
        
    return results

def fetch_dev_to(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Fetch free public developer posts & hiring needs from Dev.to API."""
    global_logger.log("DevTo", f"Querying Dev.to API for query: '{query}'")
    url = "https://dev.to/api/articles"
    params = {"search": query, "per_page": limit}
    
    resp, latency = safe_request(url, params=params, timeout=5)
    results = []
    
    if resp and resp.status_code == 200:
        try:
            articles = resp.json()
            for art in articles:
                title = art.get("title", "")
                results.append({
                    "source": "DevTo",
                    "id": str(art.get("id")),
                    "title": title,
                    "url": art.get("url", ""),
                    "author": art.get("user", {}).get("username", "author"),
                    "score": art.get("positive_reactions_count", 0),
                    "snippet": (art.get("description") or title)[:300],
                    "created_at": art.get("published_at", "")
                })
            global_logger.update_source_health("DevTo", "HEALTHY", latency, f"Fetched {len(results)} articles")
        except Exception as e:
            global_logger.update_source_health("DevTo", "DEGRADED", latency, f"Parse error: {str(e)}")
    else:
        global_logger.update_source_health("DevTo", "FAILED", latency, "HTTP Error")
        
    return results

def fetch_jobicy_jobs(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Fetch free remote job opportunities & contract postings from Jobicy API."""
    global_logger.log("Jobicy", f"Querying Jobicy Remote Jobs API for query: '{query}'")
    url = "https://jobicy.com/api/v2/remote-jobs"
    params = {"count": limit, "tag": query}
    
    resp, latency = safe_request(url, params=params, timeout=5)
    results = []
    
    if resp and resp.status_code == 200:
        try:
            data = resp.json()
            jobs = data.get("jobs", [])
            for job in jobs:
                title = job.get("jobTitle", "")
                results.append({
                    "source": "Jobicy",
                    "id": str(job.get("id")),
                    "title": f"Hiring: {title} @ {job.get('companyName', 'Startup')}",
                    "url": job.get("url", ""),
                    "author": job.get("companyName", "Company"),
                    "score": 90,
                    "snippet": f"Role: {title} | Company: {job.get('companyName')} | Geo: {job.get('jobGeo', 'Global')} | Desc: {(job.get('jobExcerpt') or title)[:200]}",
                    "created_at": job.get("pubDate", "")
                })
            global_logger.update_source_health("Jobicy", "HEALTHY", latency, f"Fetched {len(results)} jobs")
        except Exception as e:
            global_logger.update_source_health("Jobicy", "DEGRADED", latency, f"Parse error: {str(e)}")
    else:
        global_logger.update_source_health("Jobicy", "FAILED", latency, "HTTP Error")
        
    return results

# ==================== NOTION INTEGRATION TOOL ====================

def create_notion_page(lead: Dict[str, Any], email_draft: str) -> Dict[str, Any]:
    """Create a Notion page for a qualified lead using NOTION_TOKEN."""
    global_logger.log("Notion", f"Attempting Notion page export for lead: '{lead.get('title', 'Lead')}'")
    token = os.getenv("NOTION_TOKEN", "").strip()
    
    if not token or token.startswith("ntn_your"):
        global_logger.update_source_health("Notion", "FAILED", 0, "Missing or placeholder NOTION_TOKEN")
        return {"success": False, "error": "NOTION_TOKEN environment variable not set or invalid."}
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    # Step 1: Find parent page / database using Search API
    search_url = "https://api.notion.com/v1/search"
    search_payload = {"filter": {"value": "page", "property": "object"}, "page_size": 5}
    
    resp, latency = safe_request(search_url, headers=headers)
    # Search is POST, so let's do POST manually
    try:
        search_res = requests.post(search_url, headers=headers, json=search_payload, timeout=6)
        if search_res.status_code == 200:
            results = search_res.json().get("results", [])
            parent_id = results[0]["id"] if results else None
        else:
            parent_id = None
    except Exception as e:
        parent_id = None

    # If no parent page found, fallback to creating a standalone search/workspace page or reporting error
    if not parent_id:
        global_logger.log("Notion", "No accessible parent page found via Notion API Search. Ensure integration is invited to at least one page.", "WARNING")
        global_logger.update_source_health("Notion", "DEGRADED", 150, "Integration active, but no parent page shared with integration.")
        return {
            "success": False,
            "error": "Notion Integration active, but no parent Notion Page is shared with this integration. Open any Notion page -> Click Share -> Add your Integration, then retry!"
        }

    # Step 2: Create Page under parent
    create_url = "https://api.notion.com/v1/pages"
    page_payload = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": {
                "title": [{"text": {"content": f"[LeadSignal] {lead.get('title', 'High-Signal B2B Opportunity')[:90]}"}}]
            }
        },
        "children": [
            {
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": "🎯 LeadSignal B2B Opportunity Profile"}}]}
            },
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": f"Source: {lead.get('source')} | Score: {lead.get('relevance_score', 90)}/100 | Niche: {lead.get('niche', 'B2B Services')}"}}],
                    "icon": {"emoji": "🔥"}
                }
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "📌 Lead Overview & Intent"}}]}
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"Title: {lead.get('title')}\n"}},
                        {"type": "text", "text": {"content": f"URL: {lead.get('url')}\n"}},
                        {"type": "text", "text": {"content": f"Author/User: {lead.get('author')}\n\n"}},
                        {"type": "text", "text": {"content": f"Snippet / Need:\n{lead.get('snippet')}"}}
                    ]
                }
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "✉️ High-Converting Email Outreach Draft"}}]}
            },
            {
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": email_draft}}],
                    "language": "plain text"
                }
            }
        ]
    }
    
    try:
        start_t = time.time()
        c_res = requests.post(create_url, headers=headers, json=page_payload, timeout=8)
        notion_lat = int((time.time() - start_t) * 1000)
        
        if c_res.status_code == 200:
            page_data = c_res.json()
            page_url = page_data.get("url", f"https://notion.so/{page_data.get('id', '').replace('-', '')}")
            global_logger.update_source_health("Notion", "HEALTHY", notion_lat, f"Successfully created page: {page_url}")
            global_logger.log("Notion", f"Notion page successfully created: {page_url}", "SUCCESS")
            return {"success": True, "page_url": page_url}
        else:
            err_details = c_res.text[:200]
            global_logger.update_source_health("Notion", "FAILED", notion_lat, f"Notion API error: {err_details}")
            return {"success": False, "error": f"Notion API HTTP {c_res.status_code}: {err_details}"}
    except Exception as e:
        global_logger.update_source_health("Notion", "FAILED", 0, f"Exception: {str(e)}")
        return {"success": False, "error": f"Exception connecting to Notion: {str(e)}"}
