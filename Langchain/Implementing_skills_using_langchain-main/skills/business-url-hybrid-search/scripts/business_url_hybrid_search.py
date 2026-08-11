"""
business_url_hybrid_search.py

Finds the official website URL for a business given its name + address.

Search strategy (in priority order):
  1. SerpAPI Knowledge Graph  — highest confidence, Google-verified
  2. SerpAPI Organic results  — top organic hits filtered for official domains
  3. DataForSEO Organic       — cross-reference if credentials available
  4. Fallback: return all candidates with low-confidence flag

All errors are surfaced in the return dict instead of being silently swallowed,
so the caller can distinguish "no results" from "API key missing / invalid".

Required env vars (set via Streamlit sidebar):
  SERPAPI_API_KEY          — https://serpapi.com/manage-api-key  (required)
  DATAFORSEO_LOGIN         — https://app.dataforseo.com/         (optional)
  DATAFORSEO_PASSWORD      — same account                        (optional)
"""

import os
import json
import requests
from urllib.parse import urlparse

# ── Directory / social domains that are never an official business website ───
EXCLUDED_DOMAINS = {
    "yelp.com", "yellowpages.com", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "linkedin.com", "tripadvisor.com",
    "mapquest.com", "foursquare.com", "bbb.org", "groupon.com",
    "angieslist.com", "thumbtack.com", "whitepages.com", "superpages.com",
    "booking.com", "expedia.com", "hotels.com", "opentable.com",
    "zomato.com", "ubereats.com", "doordash.com", "grubhub.com",
    "pinterest.com", "youtube.com", "tiktok.com", "wikipedia.org",
    "google.com", "maps.google.com", "apple.com", "bing.com",
}


def _root_domain(url: str) -> str:
    """Return bare domain without www. prefix."""
    try:
        d = urlparse(url).netloc.lower()
        return d[4:] if d.startswith("www.") else d
    except Exception:
        return ""


def is_official_url(url: str) -> bool:
    """Return True if the URL looks like a direct business website."""
    if not url:
        return False
    d = _root_domain(url)
    if not d:
        return False
    return not any(d == ex or d.endswith("." + ex) for ex in EXCLUDED_DOMAINS)


# ─────────────────────────────────────────────────────────────────────────────
# SerpAPI
# ─────────────────────────────────────────────────────────────────────────────

def search_serpapi(query: str, api_key: str) -> dict:
    """
    Query SerpAPI Google Search.
    Returns {"knowledge_graph_url": str|None, "organic_urls": [...], "error": str|None}
    """
    result = {"knowledge_graph_url": None, "organic_urls": [], "error": None}

    if not api_key:
        result["error"] = "SERPAPI_API_KEY is not set"
        return result

    try:
        # Use requests directly — avoids serpapi SDK versioning issues
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "google",
                "q": query,
                "api_key": api_key,
                "num": 10,
            },
            timeout=15,
        )

        if resp.status_code == 401:
            result["error"] = "SerpAPI: Invalid or expired API key (401)"
            return result
        if resp.status_code == 429:
            result["error"] = "SerpAPI: Rate limit exceeded (429)"
            return result
        if resp.status_code != 200:
            result["error"] = f"SerpAPI: HTTP {resp.status_code} — {resp.text[:200]}"
            return result

        data = resp.json()

        # Knowledge Graph (highest confidence)
        kg = data.get("knowledge_graph", {})
        kg_url = kg.get("website") or kg.get("url")
        if kg_url:
            result["knowledge_graph_url"] = kg_url

        # Organic results
        for item in data.get("organic_results", []):
            link = item.get("link")
            if link:
                result["organic_urls"].append(link)

    except requests.exceptions.Timeout:
        result["error"] = "SerpAPI: Request timed out"
    except Exception as e:
        result["error"] = f"SerpAPI: {type(e).__name__}: {e}"

    return result


# ─────────────────────────────────────────────────────────────────────────────
# DataForSEO  (optional — gracefully skipped if credentials missing)
# ─────────────────────────────────────────────────────────────────────────────

def search_dataforseo(query: str, login: str, password: str) -> dict:
    """
    Query DataForSEO Google Organic Live API.
    Returns {"organic_urls": [...], "error": str|None}
    """
    result = {"organic_urls": [], "error": None}

    if not login or not password:
        result["error"] = "DataForSEO credentials not set (optional — skipped)"
        return result

    try:
        resp = requests.post(
            "https://api.dataforseo.com/v3/serp/google/organic/live/advanced",
            auth=(login, password),
            json=[{"language_code": "en", "location_code": 2840, "keyword": query}],
            headers={"content-type": "application/json"},
            timeout=20,
        )

        if resp.status_code == 401:
            result["error"] = "DataForSEO: Invalid credentials (401)"
            return result
        if resp.status_code != 200:
            result["error"] = f"DataForSEO: HTTP {resp.status_code}"
            return result

        data = resp.json()
        tasks = data.get("tasks", [])
        if tasks:
            for item in (tasks[0].get("result") or [{}])[0].get("items", []):
                if item.get("type") == "organic":
                    link = item.get("url")
                    if link:
                        result["organic_urls"].append(link)

    except requests.exceptions.Timeout:
        result["error"] = "DataForSEO: Request timed out"
    except Exception as e:
        result["error"] = f"DataForSEO: {type(e).__name__}: {e}"

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_business_url_hybrid_search(input_value: str) -> dict:
    """
    Find the official website for a business.

    Args:
        input_value: "Business Name, Full Address"
                     e.g. "Allstate, 2775 Sanders Rd, Northbrook IL 60062"
    Returns:
        {
          "success":           bool,
          "business_url":      str | None,
          "confidence":        "high" | "medium" | "low" | None,
          "source":            str,
          "candidates_checked": [str, ...],
          "errors":            {serpapi: str|None, dataforseo: str|None},
          "error":             str | None   # top-level summary if complete failure
        }
    """
    serpapi_key   = os.environ.get("SERPAPI_API_KEY", "")
    dfs_login     = os.environ.get("DATAFORSEO_LOGIN", "")
    dfs_password  = os.environ.get("DATAFORSEO_PASSWORD", "")

    if not input_value or not input_value.strip():
        return {"success": False, "error": "No input provided", "business_url": None}

    if not serpapi_key:
        return {
            "success": False,
            "business_url": None,
            "error": "SERPAPI_API_KEY is not set. Please add it in the sidebar under 🔑 Skill API Keys.",
            "errors": {"serpapi": "API key missing", "dataforseo": None},
        }

    query = f"{input_value.strip()} official website"

    # ── Run searches ──────────────────────────────────────────────────────────
    serp   = search_serpapi(query, serpapi_key)
    dfs    = search_dataforseo(query, dfs_login, dfs_password)

    errors = {
        "serpapi":    serp.get("error"),
        "dataforseo": dfs.get("error"),
    }

    # ── Priority 1: Knowledge Graph ───────────────────────────────────────────
    kg_url = serp.get("knowledge_graph_url")
    if kg_url and is_official_url(kg_url):
        return {
            "success": True,
            "business_url": kg_url,
            "confidence": "high",
            "source": "serpapi_knowledge_graph",
            "candidates_checked": [kg_url],
            "errors": errors,
        }

    # ── Priority 2: Cross-reference organic results ───────────────────────────
    all_candidates = serp.get("organic_urls", []) + dfs.get("organic_urls", [])

    # Deduplicate preserving order
    seen: set = set()
    unique: list = []
    for url in all_candidates:
        if url not in seen:
            unique.append(url)
            seen.add(url)

    official = [u for u in unique if is_official_url(u)]

    if official:
        # High confidence if same domain appears in both sources
        serp_domains = {_root_domain(u) for u in serp.get("organic_urls", [])}
        dfs_domains  = {_root_domain(u) for u in dfs.get("organic_urls", [])}
        top_domain   = _root_domain(official[0])
        confidence   = "high" if (top_domain in serp_domains and top_domain in dfs_domains) else "medium"

        return {
            "success": True,
            "business_url": official[0],
            "confidence": confidence,
            "source": "hybrid_organic" if dfs.get("organic_urls") else "serpapi_organic",
            "candidates_checked": unique[:10],
            "errors": errors,
        }

    # ── Priority 3: Return all candidates even if all are directories ─────────
    if unique:
        return {
            "success": False,
            "business_url": None,
            "confidence": "low",
            "source": "no_official_found",
            "candidates_checked": unique[:10],
            "errors": errors,
            "error": (
                "Only directory/social sites found. "
                "The business may not have its own website. "
                f"Top candidates: {', '.join(unique[:3])}"
            ),
        }

    # ── Complete failure ──────────────────────────────────────────────────────
    serp_err = errors.get("serpapi") or "no results returned"
    return {
        "success": False,
        "business_url": None,
        "confidence": None,
        "source": "no_results",
        "candidates_checked": [],
        "errors": errors,
        "error": f"No results from any source. SerpAPI status: {serp_err}",
    }


if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Allstate Northbrook IL"
    print(f"Searching for: {query}\n")
    out = run_business_url_hybrid_search(query)
    print(json.dumps(out, indent=2))
