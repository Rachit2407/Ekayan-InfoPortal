import os
import requests

# Load environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://xzbnlvqeesxwtidsupvy.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh6Ym5sdnFlZXN4d3RpZHN1cHZ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODU1NzUzODIsImV4cCI6MjEwMTE1MTM4Mn0.mU1iW3l66zb7eixpf4KqwEntCcyG90MnFNzmW74oeO4")

# If keys exist in env, load them (to override defaults)
try:
    from dotenv import load_dotenv
    load_dotenv()
    if os.getenv("SUPABASE_URL"):
        SUPABASE_URL = os.getenv("SUPABASE_URL")
    if os.getenv("SUPABASE_KEY"):
        SUPABASE_KEY = os.getenv("SUPABASE_KEY")
except ImportError:
    pass

# Auto-correct SUPABASE_URL if it is configured as the Dashboard URL instead of the REST API URL
if SUPABASE_URL and "supabase.com/dashboard/project/" in SUPABASE_URL:
    project_ref = SUPABASE_URL.split("supabase.com/dashboard/project/")[-1].split("?")[0].strip("/")
    SUPABASE_URL = f"https://{project_ref}.supabase.co"


def _get_headers(content_type=False, prefer_upsert=False):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    if content_type:
        headers["Content-Type"] = "application/json"
    if prefer_upsert:
        headers["Prefer"] = "resolution=merge-duplicates"
    return headers

def get_pending() -> list:
    """Fetch opportunities with status 'pending' from Supabase."""
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/opportunities?status=eq.pending&order=created_at.asc"
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[Supabase DB] Error fetching pending opportunities: {e}")
        return []

def save_pending(opportunities: list) -> bool:
    """Insert or update pending opportunities to Supabase."""
    if not opportunities:
        return True
    
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/opportunities"
    payload = []
    for opp in opportunities:
        item = opp.copy()
        if "status" not in item:
            item["status"] = "pending"
        payload.append(item)
        
    try:
        resp = requests.post(
            url, 
            headers=_get_headers(content_type=True, prefer_upsert=True), 
            json=payload, 
            timeout=15
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Supabase DB] Error saving pending opportunities: {e}")
        if 'resp' in locals():
            print(f"[Supabase DB] Response: {resp.text}")
        return False

def update_opportunity_status(opp_id: str, status: str) -> bool:
    """Update status of a specific opportunity by ID."""
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/opportunities?id=eq.{opp_id}"
    payload = {"status": status}
    try:
        resp = requests.patch(
            url, 
            headers=_get_headers(content_type=True), 
            json=payload, 
            timeout=10
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Supabase DB] Error updating status for '{opp_id}': {e}")
        if 'resp' in locals():
            print(f"[Supabase DB] Response: {resp.text}")
        return False

def get_bot_state() -> dict:
    """Fetch bot queue state from Supabase."""
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/bot_state?key=eq.state_queue&select=value"
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list) and len(data) > 0:
            return data[0].get("value", {})
        return {}
    except Exception as e:
        print(f"[Supabase DB] Error fetching bot state: {e}")
        return {}

def save_bot_state(state_dict: dict) -> bool:
    """Save bot queue state to Supabase."""
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/bot_state"
    payload = {
        "key": "state_queue",
        "value": state_dict
    }
    try:
        resp = requests.post(
            url, 
            headers=_get_headers(content_type=True, prefer_upsert=True), 
            json=payload, 
            timeout=10
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Supabase DB] Error saving bot state: {e}")
        if 'resp' in locals():
            print(f"[Supabase DB] Response: {resp.text}")
        return False

def get_existing_opportunities_from_supabase() -> tuple:
    """Fetch all opportunity titles and links/source_urls to prevent duplicates."""
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/opportunities?select=title,link,source_url"
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=10)
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
        print(f"[Supabase DB] Error fetching existing opportunities: {e}")
        return set(), set()
