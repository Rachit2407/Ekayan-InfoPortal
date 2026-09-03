"""
Ekayan Info Portal — WhatsApp Notifier & Bot Logic
===================================================
Handles:
1. Sending student group notifications when an opportunity is approved.
2. Sending admin notifications about newly scraped opportunities.
3. Parsing and executing admin commands (APPROVE <n>, REJECT <n>, LIST) received via webhook.
"""

import os
import sys
import json
import requests
import re
from datetime import datetime, date
from dotenv import load_dotenv
import db

# Load environment variables
load_dotenv()

WHATSAPP_TOKEN   = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID  = os.getenv("PHONE_NUMBER_ID", "")
ADMIN_WAID       = os.getenv("ADMIN_WAID", "")
STUDENT_GROUP_ID = os.getenv("STUDENT_GROUP_ID", "")
WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"

print(f"[DEBUG WA Config] WHATSAPP_ENABLED={WHATSAPP_ENABLED}")
print(f"[DEBUG WA Config] WHATSAPP_TOKEN length={len(WHATSAPP_TOKEN) if WHATSAPP_TOKEN else 0}")
print(f"[DEBUG WA Config] PHONE_NUMBER_ID={PHONE_NUMBER_ID[:4] if PHONE_NUMBER_ID else 'empty'}...")
print(f"[DEBUG WA Config] ADMIN_WAID={ADMIN_WAID[:4] if ADMIN_WAID else 'empty'}...")


META_API_URL = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
STATE_FILE = "state.json"
PENDING_FILE = "pending.json"

# Force UTF-8 encoding on Windows to prevent console print crashes
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


# ─── JSON Data Helpers ────────────────────────────────────────────────────────
def load_json_file(filepath):
    if not os.path.exists(filepath):
        if filepath == STATE_FILE:
            return {}
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        if filepath == STATE_FILE:
            return {}
        return []


def save_json_file(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving {filepath}: {e}")


# ─── WhatsApp Sending Utilities ──────────────────────────────────────────────
def send_whatsapp_text(to_number, text_message) -> bool:
    """Sends a basic raw text message to any verified number."""
    if not WHATSAPP_ENABLED:
        print("[WA Notifier] WhatsApp is disabled (WHATSAPP_ENABLED is not true).")
        return False
    if not WHATSAPP_TOKEN:
        print("[WA Notifier] Missing WHATSAPP_TOKEN in environment.")
        return False
    if not PHONE_NUMBER_ID:
        print("[WA Notifier] Missing PHONE_NUMBER_ID in environment.")
        return False

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"preview_url": True, "body": text_message}
    }
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        print(f"[WA Notifier] Sending HTTP POST to Meta API...")
        resp = requests.post(META_API_URL, json=payload, headers=headers, timeout=15)
        print(f"[WA Notifier] Response Status Code: {resp.status_code}")
        print(f"[WA Notifier] Response Body: {resp.text}")
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"  ⚠ Failed to send WA text to {to_number}: {e}")
        if 'resp' in locals():
            print(f"    API Response: {resp.text}")
        return False


def send_opportunity_notification(opportunity: dict) -> bool:
    """
    Sends a beautifully formatted student alert to the student group channel.
    """
    if not STUDENT_GROUP_ID:
        print("  ⚠ STUDENT_GROUP_ID not configured in .env. Skipping notification.")
        return False

    title        = opportunity.get("title", "New Opportunity")
    organization = opportunity.get("organization", "Unknown")
    category     = opportunity.get("category", "general").title()
    deadline     = opportunity.get("deadline") or "Not specified"
    description  = (opportunity.get("description") or "")[:250].strip()
    link         = opportunity.get("link") or opportunity.get("source_url", "")

    if deadline and deadline != "Not specified":
        try:
            from datetime import datetime
            d = datetime.strptime(deadline, "%Y-%m-%d")
            deadline = d.strftime("%d %b %Y")
        except Exception:
            pass

    message = (
        f"🎓 *New Opportunity — Ekayan Foundation*\n\n"
        f"📌 *{title}*\n"
        f"🏫 {organization}\n"
        f"🏷️ Category: {category}\n"
        f"📅 Deadline: {deadline}\n\n"
        f"📝 {description}...\n\n"
        f"🔗 *Apply / More Info:*\n{link}\n\n"
        f"──────────────────\n"
        f"⚠️ _Shared for information only. Please verify the eligibility, deadline, fees and other details on the official provider website before applying. Ekayan does not guarantee the accuracy or outcome of this opportunity._\n\n"
        f"_Powered by Ekayan Info Portal_"
    )

    return send_whatsapp_text(STUDENT_GROUP_ID, message)


def parse_command(text: str):
    """Normalize and parse admin command text into (command, list_of_numbers_or_None)."""
    text = text.strip()
    
    # Match: LIST (any case, optional trailing words/symbols)
    if re.match(r'^list\b', text, re.IGNORECASE):
        return ("LIST", None)
        
    # Match: REJECT EXPIRED (any case)
    if re.match(r'^reject\s+expired\b', text, re.IGNORECASE):
        return ("REJECT_EXPIRED", None)
        
    # Match: APPROVE/REJECT (any case) followed by digits
    m = re.match(r'^(approve|reject)\s*(.*)', text, re.IGNORECASE)
    if m:
        cmd = m.group(1).upper()
        nums_str = m.group(2)
        nums = [int(n) for n in re.findall(r'\d+', nums_str)]
        if nums:
            return (cmd, nums)
            
    return (None, None)


def format_deadline(deadline_str: str) -> str:
    """Formats deadline with human-readable alert if closing soon."""
    if not deadline_str or str(deadline_str).strip().lower() in ["", "null", "none"]:
        return "No deadline"
    try:
        d = datetime.strptime(deadline_str, "%Y-%m-%d").date()
        days_left = (d - date.today()).days
        if days_left < 0:
            return f"{deadline_str} ❌ Expired"
        if days_left == 0:
            return f"{deadline_str} ⚠️ Closes Today!"
        if days_left <= 7:
            return f"{deadline_str} ⚠️ Expires in {days_left}d!"
        return deadline_str
    except Exception:
        return deadline_str


def send_chunked_list(to_number: str, items: list, footer: str):
    """Splits long pending lists to avoid the 4096 character WhatsApp limit."""
    header = "📋 *Pending Review Queue:*\n\n"
    MAX_WA_LENGTH = 3500
    chunks = []
    current_chunk = header
    
    for item in items:
        org = item.get("organization") or "Unknown"
        if len(org) > 40 or "unspecified" in org.lower() or "details on linked" in org.lower():
            org = "Unknown"
            
        deadline = format_deadline(item.get("deadline"))
        
        line = f"*{item['number']}.* *{item['title']}*\n"
        line += f"   🏫 {org} | 📅 {deadline}\n\n"
        
        if len(current_chunk) + len(line) > MAX_WA_LENGTH:
            chunks.append(current_chunk)
            current_chunk = "📋 *(continued)*\n\n" + line
        else:
            current_chunk += line
            
    current_chunk += footer
    chunks.append(current_chunk)
    
    for chunk in chunks:
        send_whatsapp_text(to_number, chunk)


# ─── Admin Interaction Bot Logic ─────────────────────────────────────────────
def is_deadline_expired(deadline_str: str) -> bool:
    """Returns True if the deadline date is strictly in the past."""
    if not deadline_str:
        return False
    d_str = str(deadline_str).strip()
    if d_str.lower() in ["", "null", "none", "no deadline", "flexible"]:
        return False
    try:
        # Extract YYYY-MM-DD
        match = re.search(r'\d{4}-\d{2}-\d{2}', d_str)
        if match:
            deadline_date = datetime.strptime(match.group(0), "%Y-%m-%d").date()
            return deadline_date < date.today()
    except Exception as e:
        print(f"[WA Notifier] Error parsing deadline '{deadline_str}': {e}")
    return False


# ─── Admin Interaction Bot Logic ─────────────────────────────────────────────
def notify_admin_new_opportunities(new_items: list):
    """
    Called by scraper.py. Sends the admin a numbered list of new items to approve.
    Saves the list mapping to state.json.
    """
    if not ADMIN_WAID:
        print("[WA Notifier] Missing ADMIN_WAID in environment.")
        return
    if not new_items:
        print("[WA Notifier] No new items to notify admin about.")
        return

    # Load existing state or start fresh
    state = db.get_bot_state()
    if not isinstance(state, dict):
        state = {}
    
    pending_review = state.get("pending_review", [])
    
    # Filter out expired items before adding to queue
    valid_new_items = []
    expired_count = 0
    for item in new_items:
        if is_deadline_expired(item.get("deadline")):
            print(f"[WA Notifier] Auto-rejecting expired scraped opportunity: {item.get('title')} ({item.get('deadline')})")
            db.update_opportunity_status(item.get("id"), "rejected")
            expired_count += 1
        else:
            valid_new_items.append(item)

    if not valid_new_items:
        print(f"[WA Notifier] All {len(new_items)} new opportunities were auto-rejected as expired.")
        if expired_count > 0:
            send_whatsapp_text(ADMIN_WAID, f"🧹 *Ekayan Scraper Run:* Auto-rejected {expired_count} newly scraped opportunities because their deadlines were in the past.")
        return

    # Add valid new items to the review queue
    for item in valid_new_items:
        pending_review.append({
            "number": 0,
            "id": item.get("id"),
            "title": item.get("title"),
            "organization": item.get("organization"),
            "deadline": item.get("deadline")
        })

    # Re-index all numbers from 1 to N
    for idx, item in enumerate(pending_review):
        item["number"] = idx + 1

    state["pending_review"] = pending_review
    db.save_bot_state(state)

    # Format the WhatsApp message to Admin
    msg = f"🔔 *Ekayan Scraper — {len(valid_new_items)} New Opportunities Found!*\n"
    if expired_count > 0:
        msg += f"🧹 _(Also auto-rejected {expired_count} expired opportunities)_\n"
    msg += "\n"
    
    for item in pending_review[-len(valid_new_items):]:
        org = item.get("organization") or "Unknown"
        if len(org) > 40 or "unspecified" in org.lower() or "details on linked" in org.lower():
            org = "Unknown"
            
        deadline = format_deadline(item.get("deadline"))
        msg += f"*{item['number']}.* *{item['title']}*\n"
        msg += f"   🏫 {org} | 📅 {deadline}\n\n"
    
    msg += "Reply:\n"
    msg += "👉 *APPROVE <number>* (e.g. `APPROVE 1`)\n"
    msg += "👉 *REJECT <number>* (e.g. `REJECT 2`)\n"
    msg += "👉 *LIST* (to view all pending opportunities)"

    send_whatsapp_text(ADMIN_WAID, msg)


def handle_incoming_whatsapp_message(payload: dict):
    """
    Parses incoming messages from Meta Webhook and processes admin commands.
    """
    try:
        # Extract message details
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        messages = value.get("messages", [])
        
        if not messages:
            return
            
        message = messages[0]
        from_number = message.get("from")
        msg_type = message.get("type")
        
        # We only care about text messages from the authorized Admin
        if msg_type != "text" or from_number != ADMIN_WAID:
            print(f"[WA Bot] Ignored message from unauthorized number: {from_number}")
            return
            
        text = message.get("text", {}).get("body", "").strip()
        if not text:
            return
            
        print(f"[WA Bot] Received message from Admin: '{text}'")
        
        # Command Routing
        command, nums = parse_command(text)
        
        if command == "LIST":
            send_pending_list_to_admin()
        elif command == "REJECT_EXPIRED":
            reject_expired_items()
        elif command in ["APPROVE", "REJECT"] and nums:
            process_admin_decision(command, nums)
        else:
            send_whatsapp_text(ADMIN_WAID, "❓ Unknown command.\nAvailable commands:\n• `LIST`\n• `APPROVE <numbers>` (e.g., `approve 1,2` or `approve 1 2`)\n• `REJECT <numbers>`\n• `REJECT EXPIRED`")
            
    except Exception as e:
        print(f"[WA Bot] Exception inside webhook handler: {e}")
 
 
def send_pending_list_to_admin():
    """Sends current list of pending numbered opportunities to the admin."""
    state = db.get_bot_state()
    pending_review = state.get("pending_review", [])
    
    if not pending_review:
        send_whatsapp_text(ADMIN_WAID, "✅ No items currently pending review.")
        return
        
    footer = "Reply:\n• `APPROVE <number>`\n• `REJECT <number>`\n• `REJECT EXPIRED`"
    send_chunked_list(ADMIN_WAID, pending_review, footer)


def reject_expired_items():
    """Finds all expired items in the pending queue, rejects them in DB, and removes them from the queue."""
    state = db.get_bot_state()
    pending_review = state.get("pending_review", [])
    
    if not pending_review:
        send_whatsapp_text(ADMIN_WAID, "✅ No items currently pending review.")
        return
        
    expired_items = []
    valid_items = []
    
    for item in pending_review:
        if is_deadline_expired(item.get("deadline")):
            expired_items.append(item)
        else:
            valid_items.append(item)
            
    if not expired_items:
        send_whatsapp_text(ADMIN_WAID, "✅ No expired items found in the pending queue.")
        return
        
    # Process rejection for each expired item in Supabase
    for item in expired_items:
        db.update_opportunity_status(item.get("id"), "rejected")
        
    # Re-index remaining from 1 onwards
    for idx, item in enumerate(valid_items):
        item["number"] = idx + 1
        
    state["pending_review"] = valid_items
    db.save_bot_state(state)
    
    # Send summary message
    msg = f"🗑️ *Rejected & Removed {len(expired_items)} Expired Items:*\n"
    for item in expired_items:
        msg += f"• {item.get('title')} ({item.get('deadline')})\n"
    msg += "\n👉 Type `LIST` to see the updated queue (numbers are re-indexed from 1)."
    send_whatsapp_text(ADMIN_WAID, msg)


def process_admin_decision(action, item_numbers):
    """Approves or rejects multiple numbered opportunities, then re-indexes the remaining ones."""
    state = db.get_bot_state()
    pending_review = state.get("pending_review", [])
    
    if not pending_review:
        send_whatsapp_text(ADMIN_WAID, "⚠ No opportunities currently in review queue.")
        return

    # Find matching entries based on original numbers
    matches = []
    for num in item_numbers:
        for entry in pending_review:
            if entry.get("number") == num:
                if entry not in matches:
                    matches.append(entry)
                break

    not_found = [num for num in item_numbers if not any(e.get("number") == num for e in pending_review)]
    
    if not matches:
        send_whatsapp_text(ADMIN_WAID, f"⚠ None of the requested numbers {item_numbers} were found in the active queue.")
        return

    # Fetch all pending items from Supabase in one request for performance
    pending = db.get_pending()
    pending_map = {item.get("id"): item for item in pending}

    success_titles = []
    missing_db_titles = []
    tg_failed_titles = []

    # Process each matched item
    for match in matches:
        opp_id = match.get("id")
        title = match.get("title")
        
        target_item = pending_map.get(opp_id)
        if not target_item:
            missing_db_titles.append(title)
            continue

        # Update status in Supabase
        db.update_opportunity_status(opp_id, "approved" if action == "APPROVE" else "rejected")
        
        if action == "APPROVE":
            # Post to Telegram channel
            tg_success = False
            try:
                from telegram_notify import notify_channel_new_opportunity
                tg_success = notify_channel_new_opportunity(target_item)
            except Exception as tg_err:
                print(f"[Telegram Notify] Error posting to Telegram: {tg_err}")

            if not tg_success:
                tg_failed_titles.append(title)

            # Post to WhatsApp student group
            send_opportunity_notification(target_item)
            
            # Save to live list (opportunities.json) for web UI
            live = load_json_file("opportunities.json")
            if not isinstance(live, list):
                live = []
            live.append({
                "id": target_item.get("id"),
                "category": target_item.get("category"),
                "title": target_item.get("title"),
                "organization": target_item.get("organization"),
                "deadline": target_item.get("deadline"),
                "description": target_item.get("description"),
                "link": target_item.get("link") or target_item.get("source_url")
            })
            save_json_file("opportunities.json", live)
            
            # Rate limit guard: wait 1 second between batch approvals to prevent Telegram rate limit issues
            import time
            time.sleep(1.0)
            
        success_titles.append(title)

    # Remove processed matches from local state queue and re-index the remaining items
    matched_ids = {m.get("id") for m in matches if m.get("title") not in missing_db_titles}
    pending_review = [e for e in pending_review if e.get("id") not in matched_ids]
    
    # Re-index remaining from 1 onwards
    for idx, item in enumerate(pending_review):
        item["number"] = idx + 1

    state["pending_review"] = pending_review
    db.save_bot_state(state)

    # Construct the summary message to admin
    summary_msg = f"⚙️ *Batch Command Results:*\n\n"
    if success_titles:
        action_verb = "Approved & Published" if action == "APPROVE" else "Rejected & Removed"
        summary_msg += f"✅ *{action_verb} ({len(success_titles)} items):*\n"
        for t in success_titles:
            suffix = " (⚠️ Telegram post failed)" if t in tg_failed_titles else ""
            summary_msg += f"• {t}{suffix}\n"
        summary_msg += "\n"

    if missing_db_titles:
        summary_msg += f"⚠ *No Longer in Pending DB ({len(missing_db_titles)} items):*\n"
        for t in missing_db_titles:
            summary_msg += f"• {t}\n"
        summary_msg += "\n"

    if not_found:
        summary_msg += f"❓ *Numbers Not Found in Queue:* {', '.join(map(str, not_found))}\n\n"

    summary_msg += "👉 Type `LIST` to see the updated queue (numbers are re-indexed from 1)."
    send_whatsapp_text(ADMIN_WAID, summary_msg)


# ─── Direct Script Run ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  WhatsApp Notifier & Bot — Test Mode")
    print("=" * 50)
    
    if not WHATSAPP_ENABLED:
        print("\n⚠ Bot is currently disabled. Set WHATSAPP_ENABLED=true in .env to run.")
    else:
        print(f"Bot enabled.")
        print(f"Admin number: {ADMIN_WAID}")
        print(f"Group ID: {STUDENT_GROUP_ID}")
        
        # Send a test hello message
        print("\nSending hello test message to Admin...")
        send_whatsapp_text(ADMIN_WAID, "👋 Hello! The Ekayan Bot system is initialized and ready.")
        print("✅ Check your WhatsApp to see if you received the greeting!")
