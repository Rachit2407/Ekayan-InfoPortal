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
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

WHATSAPP_TOKEN   = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID  = os.getenv("PHONE_NUMBER_ID", "")
ADMIN_WAID       = os.getenv("ADMIN_WAID", "")
STUDENT_GROUP_ID = os.getenv("STUDENT_GROUP_ID", "")
WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"

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
    if not WHATSAPP_ENABLED or not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
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
        resp = requests.post(META_API_URL, json=payload, headers=headers, timeout=15)
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
        f"_Powered by Ekayan Info Portal_"
    )

    return send_whatsapp_text(STUDENT_GROUP_ID, message)


# ─── Admin Interaction Bot Logic ─────────────────────────────────────────────
def notify_admin_new_opportunities(new_items: list):
    """
    Called by scraper.py. Sends the admin a numbered list of new items to approve.
    Saves the list mapping to state.json.
    """
    if not ADMIN_WAID or not new_items:
        return

    # Load existing state or start fresh
    state = load_json_file(STATE_FILE)
    if not isinstance(state, dict):
        state = {}
    
    pending_review = state.get("pending_review", [])
    
    # Add new items to the review queue with sequential numbers
    start_num = len(pending_review) + 1
    for i, item in enumerate(new_items):
        pending_review.append({
            "number": start_num + i,
            "id": item.get("id"),
            "title": item.get("title"),
            "organization": item.get("organization"),
            "deadline": item.get("deadline")
        })

    state["pending_review"] = pending_review
    save_json_file(STATE_FILE, state)

    # Format the WhatsApp message to Admin
    msg = f"🔔 *Ekayan Scraper — {len(new_items)} New Opportunities Found!*\n\n"
    for item in pending_review[start_num-1:]:
        deadline = item.get("deadline") or "No deadline"
        msg += f"{item['number']}️⃣ *{item['title']}*\n"
        msg += f"   🏫 {item['organization']} | 📅 {deadline}\n\n"
    
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
        print(f"[WA Bot] Received message from Admin: '{text}'")
        
        # Command Routing
        parts = text.split()
        if not parts:
            return
            
        command = parts[0].upper()
        
        if command == "LIST":
            send_pending_list_to_admin()
        elif command in ["APPROVE", "REJECT"] and len(parts) >= 2:
            try:
                num = int(parts[1])
                process_admin_decision(command, num)
            except ValueError:
                send_whatsapp_text(ADMIN_WAID, "⚠ Invalid format. Use: `APPROVE 1` or `REJECT 1`.")
        else:
            send_whatsapp_text(ADMIN_WAID, "❓ Unknown command.\nAvailable commands:\n• `LIST`\n• `APPROVE <number>`\n• `REJECT <number>`")
            
    except Exception as e:
        print(f"[WA Bot] Exception inside webhook handler: {e}")


def send_pending_list_to_admin():
    """Sends current list of pending numbered opportunities to the admin."""
    state = load_json_file(STATE_FILE)
    pending_review = state.get("pending_review", [])
    
    if not pending_review:
        send_whatsapp_text(ADMIN_WAID, "✅ No items currently pending review.")
        return
        
    msg = "📋 *Pending Review Queue:*\n\n"
    for item in pending_review:
        deadline = item.get("deadline") or "No deadline"
        msg += f"{item['number']}️⃣ *{item['title']}*\n"
        msg += f"   🏫 {item['organization']} | 📅 {deadline}\n\n"
        
    msg += "Reply:\n• `APPROVE <number>`\n• `REJECT <number>`"
    send_whatsapp_text(ADMIN_WAID, msg)


def process_admin_decision(action, item_number):
    """Approves or rejects a numbered opportunity and updates local json files."""
    state = load_json_file(STATE_FILE)
    pending_review = state.get("pending_review", [])
    
    # Find the opportunity in state list
    match = None
    for entry in pending_review:
        if entry.get("number") == item_number:
            match = entry
            break
            
    if not match:
        send_whatsapp_text(ADMIN_WAID, f"⚠ Opportunity #{item_number} not found in the active list. Type `LIST` to see active items.")
        return
        
    opp_id = match.get("id")
    title = match.get("title")
    
    # Update pending.json
    pending = load_json_file(PENDING_FILE)
    target_item = None
    for item in pending:
        if item.get("id") == opp_id:
            target_item = item
            if action == "APPROVE":
                item["status"] = "approved"
            else:
                item["status"] = "rejected"
            break
            
    if not target_item:
        send_whatsapp_text(ADMIN_WAID, f"⚠ Opportunity '{title}' no longer exists in pending.json.")
        return
        
    # Save the updated pending.json
    save_json_file(PENDING_FILE, pending)
    
    # Remove from state.json pending queue
    pending_review = [e for e in pending_review if e.get("number") != item_number]
    state["pending_review"] = pending_review
    save_json_file(STATE_FILE, state)
    
    if action == "APPROVE":
        # Post to the student group channel
        wa_success = send_opportunity_notification(target_item)
        
        # Save to live list (opportunities.json) for web UI
        live = load_json_file("opportunities.json")
        # Ensure it's a list
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
        
        status_msg = f"✅ Approved: *{title}* has been posted to the students group!"
        if not wa_success:
            status_msg += "\n(Note: WhatsApp API transmission failed. Check logs.)"
        send_whatsapp_text(ADMIN_WAID, status_msg)
    else:
        send_whatsapp_text(ADMIN_WAID, f"❌ Rejected: *{title}* was removed from the queue.")


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
