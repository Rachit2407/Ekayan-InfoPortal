import http.server
import socketserver
import subprocess
import sys
import json
import os

# Force UTF-8 on Windows to prevent emoji encoding crashes
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PORT = 8000
PENDING_FILE = "pending.json"


def load_env():
    """Load .env file if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def load_pending():
    if not os.path.exists(PENDING_FILE):
        return []
    with open(PENDING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_pending(data):
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class DevServerHandler(http.server.SimpleHTTPRequestHandler):

    def read_body(self):
        """Read and parse the JSON request body."""
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        body = self.rfile.read(length)
        try:
            return json.loads(body.decode('utf-8'))
        except Exception:
            return {}

    def send_json(self, status_code, data):
        """Helper to send a JSON response."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        # ── Webhook Verification for Meta Cloud API ──────────────────────────
        if self.path.startswith('/webhook'):
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            
            mode = query.get('hub.mode', [''])[0]
            token = query.get('hub.verify_token', [''])[0]
            challenge = query.get('hub.challenge', [''])[0]
            
            verify_token = os.getenv("WEBHOOK_VERIFY_TOKEN", "ekayan_bot_secret_2026")
            
            if mode == 'subscribe' and token == verify_token:
                print("\n[Dev Server] ✅ Webhook verification SUCCESS!")
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(challenge.encode('utf-8'))
            else:
                print("\n[Dev Server] ❌ Webhook verification FAILED! Token mismatch.")
                self.send_response(403)
                self.end_headers()
        else:
            # Fallback to serving static html/js/css files
            super().do_GET()

    def do_POST(self):

        # ── /run-scraper ──────────────────────────────────────────────────────
        if self.path == '/run-scraper':
            print("\n[Dev Server] Triggering scraper.py...")
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

                status_code = 200
                response_data = {
                    "success": True,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }

                if result.returncode != 0:
                    status_code = 500
                    response_data["success"] = False
                    print(f"\n[Dev Server] ❌ Scraper failed (exit {result.returncode})")
                    if result.stderr:
                        print(f"--- STDERR ---\n{result.stderr}")
                    if result.stdout:
                        print(f"--- STDOUT ---\n{result.stdout}")

            except Exception as e:
                status_code = 500
                response_data = {"success": False, "error": str(e)}
                print(f"\n[Dev Server] ❌ Exception: {e}")

            self.send_json(status_code, response_data)

        # ── /approve-opportunity ──────────────────────────────────────────────
        elif self.path == '/approve-opportunity':
            body = self.read_body()
            opp_id = body.get("id")

            if not opp_id:
                self.send_json(400, {"success": False, "error": "Missing opportunity id"})
                return

            # Update status in pending.json
            pending = load_pending()
            item = None
            for entry in pending:
                if entry.get("id") == opp_id:
                    entry["status"] = "approved"
                    item = entry
                    break

            if not item:
                self.send_json(404, {"success": False, "error": f"Opportunity '{opp_id}' not found in pending.json"})
                return

            save_pending(pending)
            print(f"\n[Dev Server] ✅ Approved: {item.get('title')}")

            # Fire WhatsApp notification
            wa_sent = False
            try:
                from whatsapp_notify import send_opportunity_notification
                wa_sent = send_opportunity_notification(item)
            except Exception as e:
                print(f"[Dev Server] ⚠ WhatsApp notification skipped: {e}")

            self.send_json(200, {
                "success": True,
                "whatsapp_sent": wa_sent,
                "opportunity": item
            })

        # ── /webhook (Incoming WhatsApp Messages) ─────────────────────────────
        elif self.path == '/webhook':
            body = self.read_body()
            
            # Run the command parser from whatsapp_notify module
            try:
                from whatsapp_notify import handle_incoming_whatsapp_message
                handle_incoming_whatsapp_message(body)
            except Exception as e:
                print(f"[Dev Server] ⚠ Error handling incoming webhook message: {e}")
                
            self.send_json(200, {"status": "ok"})

        else:
            self.send_error(404, "File not found")

    def do_OPTIONS(self):
        """Support CORS preflight requests."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()


# Allow port reuse to prevent address-already-in-use errors
socketserver.TCPServer.allow_reuse_address = True

if __name__ == "__main__":
    load_env()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir:
        os.chdir(script_dir)

    with socketserver.TCPServer(("", PORT), DevServerHandler) as httpd:
        print(f"\n==================================================")
        print(f"   Ekayan Info Portal — Local Dev Server")
        print(f"   Running on: http://localhost:{PORT}")
        print(f"   Press Ctrl+C to stop.")
        print(f"==================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[Dev Server] Shutting down.")
