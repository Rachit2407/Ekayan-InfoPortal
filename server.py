import os
import sys
import json
import subprocess
from flask import Flask, request, jsonify, send_from_directory
import db

# Force UTF-8 on Windows to prevent emoji encoding crashes
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PENDING_FILE = "pending.json"

def load_env():
    """Load .env file if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

def load_pending():
    return db.get_pending()

def save_pending(data):
    return db.save_pending(data)

# Initialize Flask app
# Serving static files directly from the current directory
app = Flask(__name__, static_folder='.', static_url_path='')

@app.after_request
def add_cors_headers(response):
    """Add CORS headers to all responses."""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/')
def serve_portal():
    """Serve the main portal page."""
    return send_from_directory('.', 'portal.html')

@app.route('/admin')
def serve_admin():
    """Serve the admin control panel."""
    return send_from_directory('.', 'admin.html')

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Verify webhook with Meta."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    verify_token = os.getenv("WEBHOOK_VERIFY_TOKEN", "ekayan_bot_secret_2026")
    
    if mode == 'subscribe' and token == verify_token:
        print("\n[Server] ✅ Webhook verification SUCCESS!")
        return challenge, 200
    else:
        print("\n[Server] ❌ Webhook verification FAILED! Token mismatch.")
        return "Forbidden", 403

import threading

# Guard against concurrent webhook processing race condition
seen_message_ids_lock = threading.Lock()
in_memory_seen_ids = set()

def safe_handle_message(body):
    global in_memory_seen_ids
    try:
        # Check if it has a message
        entry = body.get("entry", [])
        if not entry:
            return
        changes = entry[0].get("changes", [])
        if not changes:
            return
        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return
            
        message = messages[0]
        message_id = message.get("id")
        if not message_id:
            return
            
        # Deduplicate using an in-memory lock first
        with seen_message_ids_lock:
            if message_id in in_memory_seen_ids:
                print(f"[Server] ⏭ Duplicate message ID {message_id} ignored (in-memory lock).")
                return
            in_memory_seen_ids.add(message_id)
            if len(in_memory_seen_ids) > 1000:
                in_memory_seen_ids = set(list(in_memory_seen_ids)[-500:])

        # Check if already processed in database (persistent backup)
        state = db.get_bot_state()
        seen_ids = state.get("seen_message_ids", [])
        if not isinstance(seen_ids, list):
            seen_ids = []
            
        if message_id in seen_ids:
            print(f"[Server] ⏭ Duplicate message ID {message_id} ignored (DB check).")
            return
            
        # Mark this message ID as seen in database
        seen_ids = ([message_id] + seen_ids)[:100]
        state["seen_message_ids"] = seen_ids
        db.save_bot_state(state)
        
        # Now process
        from whatsapp_notify import handle_incoming_whatsapp_message
        handle_incoming_whatsapp_message(body)
    except Exception as e:
        print(f"[Server] ⚠ Error in background webhook processing: {e}")

@app.route('/webhook', methods=['POST'])
def receive_webhook():
    """Handle incoming message webhook from Meta."""
    body = request.get_json(force=True, silent=True) or {}
    
    # Return 200 OK instantly to Meta, process message in background
    thread = threading.Thread(target=safe_handle_message, args=(body,))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "ok"}), 200

@app.route('/run-scraper', methods=['POST'])
def run_scraper():
    """Run the scraper.py script."""
    print("\n[Server] Triggering scraper.py...")
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        scraper_path = os.path.join(script_dir, 'scraper.py')

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            [sys.executable, scraper_path],
            capture_output=True,
            encoding="utf-8",
            cwd=script_dir,
            env=env
        )

        success = (result.returncode == 0)
        status_code = 200 if success else 500
        response_data = {
            "success": success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }

        if not success:
            print(f"\n[Server] ❌ Scraper failed (exit {result.returncode})")
            if result.stderr:
                print(f"--- STDERR ---\n{result.stderr}")
            if result.stdout:
                print(f"--- STDOUT ---\n{result.stdout}")

    except Exception as e:
        status_code = 500
        response_data = {"success": False, "error": str(e)}
        print(f"\n[Server] ❌ Exception: {e}")

    return jsonify(response_data), status_code

@app.route('/approve-opportunity', methods=['POST'])
def approve_opportunity():
    """Approve an opportunity manually."""
    body = request.get_json(force=True, silent=True) or {}
    opp_id = body.get("id")

    if not opp_id:
        return jsonify({"success": False, "error": "Missing opportunity id"}), 400

    pending = load_pending()
    item = None
    for entry in pending:
        if entry.get("id") == opp_id:
            entry["status"] = "approved"
            item = entry
            break

    if not item:
        return jsonify({"success": False, "error": f"Opportunity '{opp_id}' not found"}), 404

    db.update_opportunity_status(opp_id, "approved")
    print(f"\n[Server] ✅ Approved: {item.get('title')}")

    wa_sent = False
    try:
        from whatsapp_notify import send_opportunity_notification
        wa_sent = send_opportunity_notification(item)
    except Exception as e:
        print(f"[Server] ⚠ WhatsApp notification skipped: {e}")

    return jsonify({
        "success": True,
        "whatsapp_sent": wa_sent,
        "opportunity": item
    }), 200

@app.route('/list-sources', methods=['GET'])
def list_sources():
    """List all configured scrape sources."""
    try:
        sources_file = "sources.json"
        if os.path.exists(sources_file):
            with open(sources_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"sources": []}
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/test-source', methods=['POST'])
def test_source():
    """Test a source URL to auto-detect its type and discover links."""
    body = request.get_json(force=True, silent=True) or {}
    url = body.get("url", "").strip()
    filter_kws = body.get("filter_keywords", [])
    
    if not url:
        return jsonify({"success": False, "error": "Missing URL"}), 400
        
    try:
        from scraper import discover_sitemap_urls, discover_urls_from_category_page
        
        # Simple auto-detection
        is_sitemap = url.endswith(".xml") or "sitemap" in url.lower()
        
        if is_sitemap:
            detected_type = "sitemap"
            urls = discover_sitemap_urls(url, max_urls=5)
        else:
            detected_type = "category_page"
            # Split comma-separated keywords if sent as string, or use as list
            if isinstance(filter_kws, str):
                filter_kws = [k.strip() for k in filter_kws.split(",") if k.strip()]
            urls = discover_urls_from_category_page(url, max_urls=5, filter_keywords=filter_kws)
            
        return jsonify({
            "success": True,
            "type": detected_type,
            "discovered_urls": urls,
            "count": len(urls)
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/save-source', methods=['POST'])
def save_source():
    """Save a new source to sources.json."""
    body = request.get_json(force=True, silent=True) or {}
    url = body.get("url", "").strip()
    label = body.get("label", "").strip()
    category_hint = body.get("category_hint", "scholarships").strip()
    source_type = body.get("type", "").strip()
    filter_kws = body.get("link_filter_keywords", [])
    
    if not url or not label:
        return jsonify({"success": False, "error": "Missing URL or label"}), 400
        
    try:
        sources_file = "sources.json"
        if os.path.exists(sources_file):
            with open(sources_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"sources": []}
            
        sources = data.get("sources", [])
        
        # Check if already exists
        for src in sources:
            if src.get("url", "").strip().lower() == url.lower():
                return jsonify({"success": False, "error": "Source URL already exists"}), 400
                
        # Create new source
        new_src = {
            "url": url,
            "label": label,
            "category_hint": category_hint
        }
        if source_type:
            new_src["type"] = source_type
        if filter_kws:
            if isinstance(filter_kws, str):
                filter_kws = [k.strip() for k in filter_kws.split(",") if k.strip()]
            new_src["link_filter_keywords"] = filter_kws
            
        sources.append(new_src)
        data["sources"] = sources
        
        with open(sources_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/delete-source', methods=['POST'])
def delete_source():
    """Delete a source from sources.json."""
    body = request.get_json(force=True, silent=True) or {}
    url = body.get("url", "").strip()
    
    if not url:
        return jsonify({"success": False, "error": "Missing URL"}), 400
        
    try:
        sources_file = "sources.json"
        if not os.path.exists(sources_file):
            return jsonify({"success": False, "error": "sources.json not found"}), 404
            
        with open(sources_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        sources = data.get("sources", [])
        new_sources = [s for s in sources if s.get("url", "").strip().lower() != url.lower()]
        
        if len(sources) == len(new_sources):
            return jsonify({"success": False, "error": "Source URL not found"}), 404
            
        data["sources"] = new_sources
        
        with open(sources_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    load_env()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir:
        os.chdir(script_dir)

    port = int(os.environ.get("PORT", 8000))
    print(f"\n==================================================")
    print(f"   Ekayan Info Portal — Production Web Server")
    print(f"   Running on: http://localhost:{port}")
    print(f"==================================================\n")
    app.run(host="0.0.0.0", port=port, debug=False)
