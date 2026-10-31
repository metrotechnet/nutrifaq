"""
Simple HTTP server for local development that replaces environment variables.
Serves index.html from templates/ with environment variables replaced.
"""
import logging
import http.server
import socketserver
import os
import socket
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

PORT = 3000
BASE_DIR = Path(__file__).parent


def _backend_base_url() -> str:
    return (os.getenv("BACKEND_URL", "http://localhost:8080") or "http://localhost:8080").rstrip("/")


def _first_available_port(candidates: list[int]) -> int:
    for candidate in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex(("localhost", candidate)) != 0:
                return candidate
    raise RuntimeError("No available port found for frontend server.")

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        """Translate URL path to filesystem path."""
        # Decode URL encoding
        path = unquote(path)
        
        # Remove query string
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]
        
        # Serve login page at root and at /login.html for direct navigation
        if path == '/' or path == '/login.html':
            return 'SERVE_LOGIN_TEMPLATE'
        # Serve main app
        if path == '/index.html' or path == '/app' or path == '/app.html':
            return 'SERVE_TEMPLATE'
        elif path == '/users.html':
            return 'SERVE_USERS_TEMPLATE'
        elif path == '/download-manager.html':
            return 'SERVE_DOWNLOAD_MANAGER_TEMPLATE'
        # Serve static files
        elif path.startswith('/static/'):
            file_path = BASE_DIR / path.lstrip('/')
        # For api calls, return without modification (will 404, as expected)
        elif path.startswith('/api/'):
            file_path = BASE_DIR / path.lstrip('/')
        else:
            # Try to serve from root
            file_path = BASE_DIR / path.lstrip('/')
        
        return str(file_path)
    
    def do_GET(self):
        """Handle GET requests with template variable substitution."""
        path = self.translate_path(self.path)
        
        if path == 'SERVE_LOGIN_TEMPLATE':
            template_path = BASE_DIR / 'templates' / 'login.html'
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(content.encode('utf-8')))
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))

            except Exception as e:
                self.send_error(500, f"Error processing template: {str(e)}")
        elif path == 'SERVE_TEMPLATE':
            # Read and process template
            template_path = BASE_DIR / 'templates' / 'index.html'
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Send response
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(content.encode('utf-8')))
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
                
            except Exception as e:
                self.send_error(500, f"Error processing template: {str(e)}")
        elif path == 'SERVE_DOWNLOAD_MANAGER_TEMPLATE':
            template_path = BASE_DIR / 'templates' / 'download-manager.html'
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(content.encode('utf-8')))
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))

            except Exception as e:
                self.send_error(500, f"Error processing template: {str(e)}")
        elif path == 'SERVE_USERS_TEMPLATE':
            token = ""
            auth_header = self.headers.get("Authorization", "").strip()
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()
            if not token:
                query = parse_qs(urlparse(self.path).query)
                token = (query.get("token") or [""])[0].strip()

            if not token:
                self.send_error(401, "Unauthorized: missing token.")
                return

            me_req = Request(
                url=f"{_backend_base_url()}/api/users/me",
                method="GET",
                headers={"Authorization": f"Bearer {token}"},
            )
            try:
                with urlopen(me_req, timeout=15) as me_response:
                    raw_body = me_response.read().decode("utf-8", errors="replace")
                    me_payload = json.loads(raw_body) if raw_body else {}
            except (HTTPError, URLError, json.JSONDecodeError):
                self.send_error(401, "Unauthorized: invalid session token.")
                return

            role = str(me_payload.get("role", "")).strip().lower()
            if role != "admin":
                self.send_error(403, "Forbidden: admin role required.")
                return

            template_path = BASE_DIR / 'templates' / 'users.html'
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(content.encode('utf-8')))
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))

            except Exception as e:
                self.send_error(500, f"Error processing template: {str(e)}")
        else:
            # Serve static files normally
            super().do_GET()

if __name__ == '__main__':
    preferred = int(os.getenv("FRONTEND_PORT", PORT))
    fallback_ports = [preferred, 3001, 3002, 3003]
    selected_port = _first_available_port(fallback_ports)

    with socketserver.TCPServer(("localhost", selected_port), CustomHandler) as httpd:
        logger.info("%s", "=" * 60)
        logger.info("Frontend server running at: http://localhost:%s", selected_port)
        logger.info("Backend should be running at: http://localhost:8080")
        logger.info("%s", "=" * 60)
        logger.info("\nPress Ctrl+C to stop the server")
        logger.info("%s", "=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("\n\nServer stopped")
