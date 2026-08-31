"""
Ekayan Info Portal - AI Scraper
================================
This script reads website URLs from sources.json, fetches their content,
and uses the Gemini API to extract upcoming opportunities (admissions,
scholarships, fellowships, jobs). Results go into pending.json for the
Ekayan team to review and approve via the Admin Panel.

Usage:
    1. Add your GEMINI_API_KEY below (or set as environment variable)
    2. Add website URLs to sources.json
    3. Run: python scraper.py
    4. Open admin.html → "Review Queue" tab to approve/reject items

Requirements:
    pip install requests google-generativeai beautifulsoup4
"""

import json
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import uuid
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from google import genai
import sys

# Force Windows console to encode output in UTF-8 to prevent emoji crash (charmap codec errors)
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ─────────────────────────────────────────────
#  CONFIG — Add your Gemini API key here
# ─────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://xzbnlvqeesxwtidsupvy.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh6Ym5sdnFlZXN4d3RpZHN1cHZ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODU1NzUzODIsImV4cCI6MjEwMTE1MTM4Mn0.mU1iW3l66zb7eixpf4KqwEntCcyG90MnFNzmW74oeO4")

# Auto-correct SUPABASE_URL if it is configured as the Dashboard URL instead of the REST API URL
if SUPABASE_URL and "supabase.com/dashboard/project/" in SUPABASE_URL:
    project_ref = SUPABASE_URL.split("supabase.com/dashboard/project/")[-1].split("?")[0].strip("/")
    SUPABASE_URL = f"https://{project_ref}.supabase.co"

# Toggle this to True when you want to sync opportunities to Supabase cloud database
USE_SUPABASE = True
import db

SOURCES_FILE = "sources.json"
PENDING_FILE = "pending.json"
TODAY = datetime.today().strftime("%Y-%m-%d")

from difflib import SequenceMatcher

def is_similar_title(title_a: str, title_b: str) -> bool:
    """Returns True if two titles are near-duplicates."""
    a = title_a.lower().strip()
    b = title_b.lower().strip()
    
    if a == b:
        return True
        
    for suffix in [" - buddy4study", " - careers360", " - shiksha", " scholarship"]:
        if a + suffix == b or b + suffix == a:
            return True
            
    # Substring matching (e.g. "Doctoral Research Grants" and "Al Qasimi Foundation Doctoral Research Grants")
    # To prevent generic matches on small common phrases, the shorter string must be at least 20 chars
    if len(a) >= 20 and len(b) >= 20:
        if a in b or b in a:
            return True
            
    ratio = SequenceMatcher(None, a, b).ratio()
    threshold = 0.90 if min(len(a), len(b)) < 25 else 0.85
    
    if ratio >= threshold:
        if len(a) == len(b) and a[:-1] == b[:-1] and a[-1] != b[-1]:
            if a[-1].isalnum() or b[-1].isalnum():
                return False
        return True
        
    return False

# ─────────────────────────────────────────────
#  SETUP GEMINI CLIENT & SUPABASE HELPERS
# ─────────────────────────────────────────────
ai_client = None
if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
    ai_client = genai.Client(api_key=GEMINI_API_KEY)


def get_existing_opportunities_from_supabase() -> tuple:
    """Fetch existing titles and links/source_urls from Supabase to prevent duplicates."""
    if not USE_SUPABASE or not SUPABASE_URL or not SUPABASE_KEY:
        return set(), set()
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/opportunities?select=title,link,source_url"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        titles = set()
        links = set()
        for item in resp.json():
            if item.get("title"):
                titles.add(item.get("title").lower().strip())
            if item.get("link"):
                links.add(str(item.get("link")).lower().strip())
            if item.get("source_url"):
                links.add(str(item.get("source_url")).lower().strip())
        return titles, links
    except Exception as e:
        print(f"  ⚠ Could not fetch existing opportunities from Supabase: {e}")
        return set(), set()


def push_to_supabase(opportunities: list) -> None:
    """Push opportunities directly to the Supabase opportunities table using HTTP REST API."""
    if not USE_SUPABASE or not SUPABASE_URL or not SUPABASE_KEY:
        return
        
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/opportunities"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        
        # Ensure status defaults to pending
        payload = []
        for opp in opportunities:
            item = opp.copy()
            if "status" not in item:
                item["status"] = "pending"
            payload.append(item)
            
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        print(f"   ☁ Synced {len(payload)} items to Supabase cloud.")
    except Exception as e:
        print(f"  ⚠ Supabase push warning: {e}")

EXTRACTION_PROMPT = """
You are an assistant helping an Indian NGO called Ekayan Foundation find opportunities for underprivileged youth.

Below is the text content of a webpage. Extract ALL upcoming opportunities (admissions, scholarships, fellowships, or job openings) that are still open or have future deadlines, AND are open/relevant to Indian students or candidates.

CRITICAL RELEVANCE RULES:
1. ONLY include opportunities that are open to Indian citizens/students or international opportunities open to applicants from India.
2. If an opportunity is restricted to a specific country/region outside India (e.g., US only, Canada only, local Calgary residents, etc.), you MUST skip it.
3. Only extract opportunities that are genuine admissions, scholarships, fellowships, or job openings.

For each opportunity found, return a JSON array with objects using exactly this structure:
{{
  "title": "Name of the opportunity",
  "category": "admissions" | "scholarships" | "fellowships" | "jobs",
  "organization": "Name of the offering institution/company",
  "deadline": "YYYY-MM-DD format, or null if not found",
  "description": "2-3 sentence summary covering who is eligible and what is offered",
  "link": "Direct application or info URL if available, else the source URL"
}}

Today's date is {today}. Only include opportunities with deadlines in the FUTURE (after today), or where no deadline was mentioned. Skip anything already closed.

If no valid opportunities are found, return an empty array: []

Webpage content:
---
{content}
---

Return ONLY a valid JSON array. No explanation text.
""".strip()


DEADLINE_PROMPT = """
You are an assistant helping an Indian NGO called Ekayan Foundation find opportunities for underprivileged youth.

Below is the text content of a detail webpage for an opportunity (such as a scholarship or fellowship).
Extract the application deadline date for this opportunity.

Return ONLY the date in YYYY-MM-DD format (e.g. 2026-08-31) if a valid deadline date is found, or "null" if no deadline is specified or if it is not found.
Do not write any explanation, introduction, markdown code fences, or punctuation. Just return the date or "null".

Today's date is {today}.

Webpage content:
---
{content}
---

Return ONLY the YYYY-MM-DD date or "null".
""".strip()


def extract_deadline_from_detail_page(page_text: str) -> str:
    """Call Gemini to extract a deadline in YYYY-MM-DD format from detail page text."""
    if not page_text or len(page_text.strip()) < 100:
        return ""
    if not ai_client:
        return ""
        
    prompt = DEADLINE_PROMPT.format(today=TODAY, content=page_text)
    
    models_to_try = get_available_gemini_models()
    for model_name in models_to_try:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response and getattr(response, "text", None):
                raw = response.text.strip().replace("`", "").replace("'", "").replace('"', "")
                import re
                date_match = re.search(r'\d{4}-\d{2}-\d{2}', raw)
                if date_match:
                    return date_match.group(0)
        except Exception:
            pass
    return ""


def fetch_page_content(url: str, return_html: bool = False) -> str:
    """Fetch a webpage and return its content (HTML or plain text).
    If plain HTTP request fails or returns minimal content (<300 chars),
    automatically fall back to Playwright headless Chromium for JS rendering.
    """
    html_content = ""
    text_content = ""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html_content = resp.text
        
        if not return_html:
            soup = BeautifulSoup(html_content, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            from urllib.parse import urljoin
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href and not href.startswith("#") and "javascript:" not in href.lower():
                    a.replace_with(f"{a.get_text()} (Link: {urljoin(url, href)})")
            text_content = soup.get_text(separator="\n", strip=True)
    except Exception as e:
        print(f"  ℹ HTTP fetch note ({url}): {e}")

    # If HTTP text is sufficient (>= 300 chars), return it/HTML directly
    if return_html and html_content:
        return html_content
    elif not return_html and len(text_content) >= 300:
        return text_content[:15000]

    # If Playwright is explicitly disabled or we got any HTML content, avoid OOM on cloud servers
    if os.environ.get("DISABLE_PLAYWRIGHT") == "true" or (html_content and len(html_content) > 500):
        return html_content if return_html else (text_content[:15000] if text_content else "")

    # Fallback to Playwright Headless Browser with stealth settings
    try:
        from playwright.sync_api import sync_playwright
        print(f"   🎭 Low/empty static content. Running Playwright headless browser for JS rendering...")
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(
                    headless=True,
                    channel="chrome",
                    args=['--disable-blink-features=AutomationControlled']
                )
            except Exception:
                browser = p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled']
                )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                locale="en-US"
            )
            page = context.new_page()
            page.add_init_script("delete navigator.__proto__.webdriver;")
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2000)
            pw_html = page.content()
            browser.close()
            
            if return_html:
                return pw_html
                
            soup = BeautifulSoup(pw_html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            from urllib.parse import urljoin
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href and not href.startswith("#") and "javascript:" not in href.lower():
                    a.replace_with(f"{a.get_text()} (Link: {urljoin(url, href)})")
            pw_text = soup.get_text(separator="\n", strip=True)
            if len(pw_text) > len(text_content):
                print(f"   ✅ Playwright retrieved {len(pw_text)} characters.")
                return pw_text[:15000]
    except Exception as pw_err:
        print(f"  ⚠ Playwright browser fallback skipped/failed: {pw_err}")

    return html_content if return_html else (text_content[:15000] if text_content else "")


def fetch_page_text(url: str) -> str:
    """Fetch plain text content of a page."""
    return fetch_page_content(url, return_html=False)


def fetch_page_html(url: str) -> str:
    """Fetch raw HTML content of a page."""
    return fetch_page_content(url, return_html=True)


def get_available_gemini_models() -> list:
    """Return standard verified Gemini generation models."""
    return ["gemini-2.5-flash", "gemini-3.6-flash", "gemini-flash-latest", "gemini-2.5-flash-lite"]


def extract_opportunities(page_text: str, source_url: str, category_hint: str) -> list:
    """Call Gemini API via google.genai Client to extract structured opportunities."""
    if not page_text or len(page_text.strip()) < 150:
        print("  ⚠ Page text too short or empty to extract opportunities. Skipping.")
        return []
    
    if not ai_client:
        print("  ⚠ Gemini Client not initialized. Check GEMINI_API_KEY.")
        return []
        
    prompt = EXTRACTION_PROMPT.format(today=TODAY, content=page_text)
    response = None
    
    # Models list (tries auto-discovered models first, then fallback candidates)
    models_to_try = get_available_gemini_models()
    for model_name in models_to_try:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response and getattr(response, "text", None):
                break
        except Exception as e:
            if model_name != models_to_try[-1]:
                print(f"  ℹ Model {model_name} unavailable: {e}. Trying next fallback...")
            else:
                print(f"  ⚠ Gemini extraction error across models ({model_name}): {e}")
                return []
                
    if not response or not getattr(response, "text", None):
        print("  ⚠ Gemini API returned an empty or blocked response. Skipping page.")
        return []

    try:
        raw = response.text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        if raw.endswith("```"):
            raw = raw[:-3].strip()
            
        items = json.loads(raw)
        if not isinstance(items, list):
            print("  ⚠ Gemini returned invalid non-list JSON format. Skipping.")
            return []
        
        # Stamp each item with metadata
        for item in items:
            item["id"] = f"ai-{uuid.uuid4().hex[:8]}"
            item["source_url"] = source_url
            item["ai_found_on"] = TODAY
            item["status"] = "pending"  # pending | approved | rejected
            # Fallback category from hint if AI left it blank
            if not item.get("category"):
                item["category"] = category_hint or "scholarships"
                
            # If the extracted link is a root homepage (e.g. www.buddy4study.com), fall back to source_url
            link = str(item.get("link") or "").strip()
            if not link:
                item["link"] = source_url
            else:
                from urllib.parse import urlparse
                try:
                    parsed = urlparse(link)
                    if parsed.netloc and (parsed.path in ('', '/')) and not parsed.query and source_url:
                        item["link"] = source_url
                except Exception:
                    pass
        
        return items
    except Exception as e:
        print(f"  ⚠ Gemini response parsing error: {e}")
        return []


def load_json(path: str) -> list | dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def discover_sitemap_urls(sitemap_url: str, max_urls: int = 5) -> list:
    """Fetch a sitemap XML and return the latest relevant article URLs."""
    try:
        print(f"   🔍 Auto-discovering latest URLs from sitemap: {sitemap_url}...")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        resp = requests.get(sitemap_url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "xml")
        urls = [loc.text for loc in soup.find_all("loc")]
        
        # Filter for relevant terms
        keywords = ["scholarship", "admission", "fellowship", "dates", "deadline", "closing", "apply"]
        relevant_urls = []
        for u in urls:
            if u.endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            if any(k in u.lower() for k in keywords):
                relevant_urls.append(u)
                
        # Take the N most recent (bottom of sitemap)
        latest_urls = relevant_urls[-max_urls:]
        print(f"   ✅ Discovered {len(latest_urls)} latest articles to scan.")
        return latest_urls
    except Exception as e:
        print(f"  ⚠ Sitemap discovery error: {e}")
        return []


def discover_urls_from_category_page(category_url: str, max_urls: int = 5, filter_keywords: list = None) -> list:
    """Fetch a category listing page and return relevant opportunity links."""
    try:
        print(f"   🔍 Discovering links from category page: {category_url}...")
        html = fetch_page_html(category_url)
        if not html:
            return []
            
        soup = BeautifulSoup(html, "html.parser")
        links = []
        from urllib.parse import urljoin, urlparse
        
        parsed_cat = urlparse(category_url)
        cat_path = parsed_cat.path.rstrip('/')
        
        junk_terms = ["login", "signup", "auth.", "facebook", "twitter", "instagram", "youtube", "linkedin", "privacy", "terms", "about", "contact", "search"]
        default_keywords = ["exam", "admission", "scholarship", "fellowship", "result", "form", "date", "apply", "test", "course", "article", "job", "recruitment", "grant"]
        
        active_keywords = filter_keywords if filter_keywords else default_keywords

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or "javascript:" in href.lower():
                continue
                
            full_url = urljoin(category_url, href)
            parsed_full = urlparse(full_url)
            
            # Skip the category page itself or root homepage
            if full_url.rstrip("/") == category_url.rstrip("/") or parsed_full.path in ("", "/"):
                continue
                
            # Skip junk/nav links
            if any(junk in full_url.lower() for junk in junk_terms):
                continue
                
            # Check if link path is a subpath of category page OR matches keywords
            is_subpath = bool(cat_path and len(cat_path) > 1 and parsed_full.path.startswith(cat_path + "/"))
            has_kw = any(kw.lower() in full_url.lower() or kw.lower() in a.get_text().lower() for kw in active_keywords)
            
            if is_subpath or has_kw:
                if full_url not in links:
                    links.append(full_url)
                    if len(links) >= max_urls:
                        break
                        
        print(f"   ✅ Discovered {len(links)} articles from category page to scan.")
        return links
    except Exception as e:
        print(f"  ⚠ Category page discovery error: {e}")
        return []


def main():
    print("=" * 50)
    print("  Ekayan Info Portal — AI Scraper")
    print(f"  Running on: {TODAY}")
    print("=" * 50)

    # Validate API Key
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE" or not GEMINI_API_KEY.strip():
        print("\n⚠ ERROR: Gemini API Key is not configured!")
        print("Please edit scraper.py (line 31) and replace 'YOUR_GEMINI_API_KEY_HERE' with your real API key,")
        print("or set the environment variable in your terminal:")
        print("  PowerShell:  $env:GEMINI_API_KEY=\"AIzaSy...\"")
        print("  CMD:         set GEMINI_API_KEY=AIzaSy...\n")
        return

    # Load sources
    sources_data = load_json(SOURCES_FILE)
    sources = sources_data.get("sources", [])
    if not sources:
        print("\n⚠ No sources found in sources.json. Add URLs and re-run.\n")
        return
    
    # Load existing pending items (to avoid duplicates)
    existing_pending = db.get_pending() if USE_SUPABASE else []
    existing_titles = {item.get("title", "").lower().strip() for item in existing_pending if item.get("title")}
    existing_links = set()
    for item in existing_pending:
        if item.get("link"):
            existing_links.add(str(item.get("link")).lower().strip())
        if item.get("source_url"):
            existing_links.add(str(item.get("source_url")).lower().strip())
    
    # Also fetch existing titles and links from Supabase to prevent double scraping
    if USE_SUPABASE:
        db_titles, db_links = db.get_existing_opportunities_from_supabase()
        existing_titles.update(db_titles)
        existing_links.update(db_links)
    
    new_items = []
    
    run_stats = {
        "date": TODAY,
        "total_discovered_urls": 0,
        "total_scanned_urls": 0,
        "total_new_opportunities": 0,
        "sources": {},
        "errors": []
    }
    
    for source in sources:
        url = source.get("url", "")
        label = source.get("label", url)
        category_hint = source.get("category_hint", "")
        
        run_stats["sources"][label] = {
            "discovered": 0,
            "scanned": 0,
            "found": 0,
            "errors": []
        }
        
        # Check if this is a category page, a sitemap, or a direct URL
        urls_to_scan = []
        source_type = source.get("type", "")
        try:
            if source_type == "category_page":
                print(f"\n🌐 Reading Category Page: {label}")
                print(f"   Category URL: {url}")
                filter_kws = source.get("link_filter_keywords", [])
                urls_to_scan = discover_urls_from_category_page(url, max_urls=5, filter_keywords=filter_kws)
            elif url.endswith(".xml") or "sitemap" in url or source_type == "sitemap":
                print(f"\n🌐 Reading Sitemap: {label}")
                print(f"   Sitemap URL: {url}")
                urls_to_scan = discover_sitemap_urls(url, max_urls=5)
            else:
                urls_to_scan = [url]
        except Exception as e:
            print(f"  ⚠ Discovery error for {label}: {e}")
            run_stats["errors"].append(f"Discovery error ({label}): {e}")
            run_stats["sources"][label]["errors"].append(str(e))
            
        run_stats["sources"][label]["discovered"] = len(urls_to_scan)
        run_stats["total_discovered_urls"] += len(urls_to_scan)
            
        for scan_url in urls_to_scan:
            if len(urls_to_scan) > 1:
                print(f"\n   📄 Scanning discovered page: {scan_url}")
            else:
                print(f"\n🌐 Scanning: {label}")
                print(f"   URL: {scan_url}")
                
            run_stats["total_scanned_urls"] += 1
            run_stats["sources"][label]["scanned"] += 1
                 
            try:
                page_text = fetch_page_text(scan_url)
                if not page_text:
                    run_stats["sources"][label]["errors"].append(f"Empty content from {scan_url}")
                    continue
                
                found = extract_opportunities(page_text, scan_url, category_hint)
                
                # Deduplicate by title and links
                source_new_count = 0
                for item in found:
                    is_duplicate = False
                    item_title = item.get("title", "")
                    item_link = str(item.get("link") or "").lower().strip()
                    item_source = str(item.get("source_url") or "").lower().strip()
                    
                    # 1. Check title similarity
                    for existing in existing_titles:
                        if is_similar_title(item_title, existing):
                            is_duplicate = True
                            break
                            
                    # 2. Check link similarity
                    if not is_duplicate:
                        if (item_link and item_link in existing_links) or (item_source and item_source in existing_links):
                            is_duplicate = True
                            
                    if not is_duplicate:
                        link = item.get("link")
                        if link and link.startswith("http") and link != scan_url:
                            if not item.get("deadline") or str(item.get("deadline")).strip().lower() in ["", "null", "none"]:
                                print(f"      🔍 Detail scanning for deadline: {link}")
                                detail_text = fetch_page_text(link)
                                if detail_text and len(detail_text) > 150:
                                    deadline = extract_deadline_from_detail_page(detail_text)
                                    if deadline:
                                        item["deadline"] = deadline
                                        print(f"         📅 Extracted deadline: {deadline}")
                                    else:
                                        print(f"         ℹ No deadline found on detail page.")
                                        
                        new_items.append(item)
                        existing_titles.add(item_title.lower().strip())
                        if item.get("link"):
                            existing_links.add(str(item.get("link")).lower().strip())
                        if item.get("source_url"):
                            existing_links.add(str(item.get("source_url")).lower().strip())
                        source_new_count += 1
                        print(f"      ✅ Found: {item.get('title')} (Deadline: {item.get('deadline')})")
                    else:
                        print(f"      ⏭ Skipped (duplicate): {item.get('title')}")
                
                run_stats["sources"][label]["found"] += source_new_count
                run_stats["total_new_opportunities"] += source_new_count
            except Exception as scan_err:
                print(f"  ⚠ Scan error on {scan_url}: {scan_err}")
                run_stats["errors"].append(f"Scan error ({scan_url}): {scan_err}")
                run_stats["sources"][label]["errors"].append(str(scan_err))
    
    if new_items:
        if USE_SUPABASE:
            db.save_pending(new_items)
            print(f"\n🎉 Done! {len(new_items)} new opportunity/ies synced to Supabase")
            
            # Trigger WhatsApp notification to the Admin
            try:
                from whatsapp_notify import notify_admin_new_opportunities
                print("   📲 Sending notification list to WhatsApp admin...")
                notify_admin_new_opportunities(new_items)
            except Exception as wa_err:
                print(f"   ⚠ Failed to trigger WhatsApp admin notification: {wa_err}")

            print("   → Open admin.html or reply via WhatsApp to approve them.")
        else:
            save_json(PENDING_FILE, new_items)
            print(f"\n🎉 Dry Run Done! {len(new_items)} new opportunity/ies saved to local {PENDING_FILE}")
    else:
        print("\n✅ No new opportunities found this run.")
        
    # Dispatch Telegram report to Admin
    try:
        from telegram_notify import send_pipeline_run_report
        print("\n📲 Dispatching pipeline run report to Telegram...")
        send_pipeline_run_report(run_stats)
    except Exception as tg_err:
        print(f"  ⚠ Failed to send Telegram run report: {tg_err}")
    
    print()


if __name__ == "__main__":
    main()
