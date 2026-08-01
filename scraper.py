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
import uuid
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
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
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://eolzuwwnusmtvssolavt.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVvbHp1d3dudXNtdHZzc29sYXZ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk5NTAzMjIsImV4cCI6MjA5NTUyNjMyMn0.Zzu_LzCQzEZZtj3B3WD85-uWG6KMyGK1BlMxh4gbY60")

# Toggle this to True when you want to sync opportunities to Supabase cloud database
USE_SUPABASE = False

SOURCES_FILE = "sources.json"
PENDING_FILE = "pending.json"
TODAY = datetime.today().strftime("%Y-%m-%d")

# ─────────────────────────────────────────────
#  SETUP GEMINI & SUPABASE HELPERS
# ─────────────────────────────────────────────
genai.configure(api_key=GEMINI_API_KEY)


def get_existing_titles_from_supabase() -> set:
    """Fetch existing titles from Supabase to prevent duplicates."""
    if not USE_SUPABASE or not SUPABASE_URL or not SUPABASE_KEY:
        return set()
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/opportunities?select=title"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        titles = {item.get("title", "").lower() for item in resp.json() if item.get("title")}
        return titles
    except Exception as e:
        print(f"  ⚠ Could not fetch existing titles from Supabase: {e}")
        return set()


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

Below is the text content of a webpage. Extract ALL upcoming opportunities (admissions, scholarships, fellowships, or job openings) that are still open or have future deadlines.

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


def fetch_page_text(url: str) -> str:
    """Fetch a webpage and return its plain text content."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; EkayanBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove script/style noise
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:15000]  # cap at 15k chars
    except Exception as e:
        print(f"  ⚠ Could not fetch {url}: {e}")
        return ""


def extract_opportunities(page_text: str, source_url: str, category_hint: str) -> list:
    """Call Gemini API to extract structured opportunities from page text."""
    if not page_text.strip():
        return []
    
    prompt = EXTRACTION_PROMPT.format(today=TODAY, content=page_text)
    response = None
    
    # Try the latest Gemini models available on the API key
    for model_name in ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            break
        except Exception as e:
            if model_name != "gemini-flash-latest":
                print(f"  ℹ Model {model_name} failed. Trying next fallback...")
            else:
                print(f"  ⚠ Gemini extraction error ({model_name}): {e}")
                return []
                
    if not response:
        return []

    try:
        raw = response.text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        
        items = json.loads(raw)
        
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
            link = item.get("link", "").strip()
            if not link:
                item["link"] = source_url
            else:
                from urllib.parse import urlparse
                try:
                    parsed = urlparse(link)
                    # Check if the path is empty, root, or missing and there are no search parameters
                    if parsed.netloc and (parsed.path in ('', '/')) and not parsed.query and source_url:
                        item["link"] = source_url
                except Exception:
                    pass
        
        return items
    except Exception as e:
        print(f"  ⚠ Gemini processing error: {e}")
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
    existing_pending = load_json(PENDING_FILE)
    existing_titles = {item.get("title", "").lower() for item in existing_pending}
    
    # Also fetch existing titles from Supabase to prevent double scraping
    db_titles = get_existing_titles_from_supabase()
    existing_titles.update(db_titles)
    
    new_items = []
    
    for source in sources:
        url = source.get("url", "")
        label = source.get("label", url)
        category_hint = source.get("category_hint", "")
        
        # Check if this is a sitemap for auto-discovery
        urls_to_scan = []
        if url.endswith(".xml") or "sitemap" in url:
            print(f"\n🌐 Reading Sitemap: {label}")
            print(f"   Sitemap URL: {url}")
            urls_to_scan = discover_sitemap_urls(url, max_urls=5)
        else:
            urls_to_scan = [url]
            
        for scan_url in urls_to_scan:
            if len(urls_to_scan) > 1:
                print(f"\n   📄 Scanning discovered page: {scan_url}")
            else:
                print(f"\n🌐 Scanning: {label}")
                print(f"   URL: {scan_url}")
                
            page_text = fetch_page_text(scan_url)
            if not page_text:
                continue
            
            found = extract_opportunities(page_text, scan_url, category_hint)
            
            # Deduplicate by title
            for item in found:
                if item.get("title", "").lower() not in existing_titles:
                    new_items.append(item)
                    existing_titles.add(item.get("title", "").lower())
                    print(f"      ✅ Found: {item.get('title')}")
                else:
                    print(f"      ⏭ Skipped (duplicate): {item.get('title')}")
    
    if new_items:
        combined = existing_pending + new_items
        save_json(PENDING_FILE, combined)
        print(f"\n🎉 Done! {len(new_items)} new opportunity/ies added to pending.json")
        
        # Trigger WhatsApp notification to the Admin
        try:
            from whatsapp_notify import notify_admin_new_opportunities
            print("   📲 Sending notification list to WhatsApp admin...")
            notify_admin_new_opportunities(new_items)
        except Exception as wa_err:
            print(f"   ⚠ Failed to trigger WhatsApp admin notification: {wa_err}")

        push_to_supabase(new_items)
        print("   → Open admin.html or reply via WhatsApp to approve them.")
    else:
        print("\n✅ No new opportunities found this run.")
    
    print()


if __name__ == "__main__":
    main()
