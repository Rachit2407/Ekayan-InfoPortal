import os
import html
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")

def send_telegram_message(text_message: str, parse_mode: str = "HTML") -> bool:
    """Sends a message to the Telegram channel using the Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        print("[Telegram Notify] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID in env.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": text_message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Telegram Notify] Error sending message: {e}")
        if 'resp' in locals():
            print(f"[Telegram Notify] API Response: {resp.text}")
        return False

def format_opportunity_card(opp: dict) -> str:
    """Formats an opportunity into a beautiful HTML card for Telegram."""
    category = html.escape(opp.get("category", "Opportunity").strip().title())
    title = html.escape(opp.get("title", "New Alert").strip())
    org = html.escape(opp.get("organization", "N/A").strip())
    deadline = opp.get("deadline")
    desc = html.escape(opp.get("description", "").strip())
    link = opp.get("link", "").strip()

    # Format deadline
    if not deadline:
        deadline_str = "Flexible"
    else:
        # Expected format is YYYY-MM-DD
        deadline_str = str(deadline)

    # Clean description if too long (Telegram message limit is 4096, but keep it concise)
    if len(desc) > 500:
        desc = desc[:497] + "..."

    # Assign category emoji
    emoji = "🎓"
    cat_lower = category.lower()
    if "scholarship" in cat_lower:
        emoji = "💰"
    elif "fellowship" in cat_lower:
        emoji = "🤝"
    elif "admission" in cat_lower or "exam" in cat_lower:
        emoji = "📝"
    elif "job" in cat_lower or "internship" in cat_lower:
        emoji = "💼"

    card = (
        f"{emoji} <b>New Opportunity Alert</b>\n\n"
        f"<b>🎯 {title}</b>\n"
        f"🏢 <b>Organization:</b> {org}\n"
        f"🏷️ <b>Category:</b> {category}\n"
        f"📅 <b>Deadline:</b> <b>{deadline_str}</b>\n\n"
    )

    if desc:
        card += f"📝 <b>Details:</b>\n<i>{desc}</i>\n\n"

    if link:
        card += f"🔗 <a href='{link}'><b>Apply / More Info</b></a>\n"

    card += (
        f"──────────────────\n"
        f"📢 <b>Ekayan Info Portal</b>"
    )
    return card

def notify_channel_new_opportunity(opportunity: dict) -> bool:
    """Formats and broadcasts a newly approved opportunity to the Telegram channel."""
    print(f"[Telegram Notify] Preparing to send approved opportunity '{opportunity.get('title')}'")
    card_content = format_opportunity_card(opportunity)
    success = send_telegram_message(card_content, parse_mode="HTML")
    if success:
        print("[Telegram Notify] Opportunity posted successfully!")
    else:
        print("[Telegram Notify] Failed to post opportunity to channel.")
    return success


def send_pipeline_run_report(stats: dict) -> bool:
    """Sends a summary report of the scraper pipeline execution to the admin chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("[Telegram Notify] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_ADMIN_CHAT_ID in env. Skipping admin run report.")
        return False

    admin_chat_id = TELEGRAM_ADMIN_CHAT_ID

    emoji_status = "✅" if not stats.get("errors") else "⚠️"
    
    report = (
        f"{emoji_status} <b>Ekayan Scraper Run Report</b>\n"
        f"📅 <b>Date:</b> {stats.get('date', 'N/A')}\n"
        f"──────────────────\n\n"
    )
    
    # Summary of changes
    report += (
        f"📋 <b>Overall Summary:</b>\n"
        f"• <b>Total Discovered URLs:</b> {stats.get('total_discovered_urls', 0)}\n"
        f"• <b>Total Scanned URLs:</b> {stats.get('total_scanned_urls', 0)}\n"
        f"• <b>New Opportunities Found:</b> {stats.get('total_new_opportunities', 0)}\n\n"
    )
    
    # Details per source
    report += "🔍 <b>Source Details:</b>\n"
    for s_label, s_stats in stats.get("sources", {}).items():
        report += (
            f"📍 <b>{s_label}</b>\n"
            f"  ▫️ Discovered: {s_stats.get('discovered', 0)} | Scanned: {s_stats.get('scanned', 0)}\n"
            f"  ▫️ Found: {s_stats.get('found', 0)} new items\n"
        )
        if s_stats.get("errors"):
            report += f"  ❌ <b>Errors:</b> {html.escape(s_stats.get('errors')[0])}\n"
        report += "\n"
        
    if stats.get("errors"):
        report += f"⚠️ <b>Pipeline Warnings/Errors:</b>\n"
        for err in stats.get("errors")[:3]:  # Show first 3 errors to avoid length overflow
            report += f"• <i>{html.escape(str(err))}</i>\n"
        report += "\n"
        
    report += "⚙️ <i>Admin monitoring channel</i>"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": admin_chat_id,
        "text": report,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Telegram Notify] Error sending pipeline run report: {e}")
        if 'resp' in locals():
            print(f"[Telegram Notify] API Response: {resp.text}")
        return False


if __name__ == "__main__":
    # Small test block to run locally
    print("Testing Telegram Notification locally...")
    test_opp = {
        "title": "PM YASASVI Scholarship Scheme 2026",
        "organization": "Ministry of Social Justice and Empowerment",
        "category": "Scholarship",
        "deadline": "2026-08-31",
        "description": "Top-class education scholarship scheme for OBC, EBC, and DNT students studying in Class 9 to 12. Covers tuition fees and hostel allowances.",
        "link": "https://scholarships.gov.in"
    }
    
    # Check if env is set up
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        print("\n[!] Setup warning: Env variables not found. Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID to test.")
    else:
        print("Sending test card to Telegram...")
        notify_channel_new_opportunity(test_opp)
