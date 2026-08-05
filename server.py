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

@app.route('/webhook', methods=['POST'])
def receive_webhook():
    """Handle incoming message webhook from Meta."""
    body = request.get_json(force=True, silent=True) or {}
    
    try:
        from whatsapp_notify import handle_incoming_whatsapp_message
        handle_incoming_whatsapp_message(body)
    except Exception as e:
        print(f"[Server] ⚠ Error handling incoming webhook message: {e}")
        
    return jsonify({"status": "ok"}), 200

@app.route('/debug-db', methods=['GET'])
def debug_db():
    try:
        state = db.get_bot_state()
        pending = db.get_pending()
        return jsonify({
            "success": True,
            "supabase_url_prefix": db.SUPABASE_URL[:15] if db.SUPABASE_URL else None,
            "state_keys": list(state.keys()) if state else [],
            "pending_count": len(pending),
            "state_raw": state
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

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
