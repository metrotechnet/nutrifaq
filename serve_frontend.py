"""
Simple HTTP server for local development that replaces environment variables.
Serves index.html from templates/ with environment variables replaced.
"""
import http.server
import socketserver
import os
import socket
from pathlib import Path
from urllib.parse import unquote
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

PORT = 3000
BASE_DIR = Path(__file__).parent


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
        
        # Serve login page at root
        if path == '/':
            return 'SERVE_LOGIN_TEMPLATE'
        # Serve main app
        if path == '/index.html' or path == '/app' or path == '/app.html':
            return 'SERVE_TEMPLATE'
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
        else:
            # Serve static files normally
            super().do_GET()

if __name__ == '__main__':
    preferred = int(os.getenv("FRONTEND_PORT", PORT))
    fallback_ports = [preferred, 3001, 3002, 3003]
    selected_port = _first_available_port(fallback_ports)

    with socketserver.TCPServer(("localhost", selected_port), CustomHandler) as httpd:
        print("=" * 60)
        print(f"Frontend server running at: http://localhost:{selected_port}")
        print(f"Backend should be running at: http://localhost:8080")
        print("=" * 60)
        print("\nPress Ctrl+C to stop the server")
        print("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer stopped")
