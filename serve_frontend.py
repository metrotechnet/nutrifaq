"""
Simple HTTP server for local development that replaces environment variables.
Serves index.html from templates/ with environment variables replaced.
"""
import http.server
import socketserver
import os
from pathlib import Path
from urllib.parse import unquote
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

PORT = 3000
BASE_DIR = Path(__file__).parent

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        """Translate URL path to filesystem path."""
        # Decode URL encoding
        path = unquote(path)
        
        # Remove query string
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]
        
        # Serve index.html at root
        if path == '/' or path == '/index.html':
            return 'SERVE_TEMPLATE'
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
        
        if path == 'SERVE_TEMPLATE':
            # Read and process template
            template_path = BASE_DIR / 'templates' / 'index.html'
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Replace environment variables
                replacements = {
                    '{{FIREBASE_PROJECT_ID}}': os.getenv('FIREBASE_PROJECT_ID', ''),
                    '{{FIREBASE_API_KEY}}': os.getenv('FIREBASE_API_KEY', ''),
                    '{{FIREBASE_AUTH_DOMAIN}}': os.getenv('FIREBASE_AUTH_DOMAIN', ''),
                    '{{FIREBASE_STORAGE_BUCKET}}': os.getenv('FIREBASE_STORAGE_BUCKET', ''),
                    '{{FIREBASE_MESSAGING_SENDER_ID}}': os.getenv('FIREBASE_MESSAGING_SENDER_ID', ''),
                    '{{FIREBASE_APP_ID}}': os.getenv('FIREBASE_APP_ID', ''),
                    '{{FIREBASE_MEASUREMENT_ID}}': os.getenv('FIREBASE_MEASUREMENT_ID', ''),
                    '{{RECAPTCHA_SITE_KEY}}': os.getenv('RECAPTCHA_SITE_KEY', ''),
                    '{{APP_CHECK_ENABLED}}': os.getenv('APP_CHECK_ENABLED', 'false'),
                    '{{APP_CHECK_DEBUG_TOKEN}}': os.getenv('APP_CHECK_DEBUG_TOKEN', ''),
                }
                
                for placeholder, value in replacements.items():
                    content = content.replace(placeholder, value)
                
                # Send response
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
    with socketserver.TCPServer(("localhost", PORT), CustomHandler) as httpd:
        print("=" * 60)
        print(f"Frontend server running at: http://localhost:{PORT}")
        print(f"Backend should be running at: http://localhost:8080")
        print("=" * 60)
        print(f"\nFirebase Config:")
        print(f"  Project ID: {os.getenv('FIREBASE_PROJECT_ID', 'NOT SET')}")
        print(f"  App ID: {os.getenv('FIREBASE_APP_ID', 'NOT SET')}")
        print(f"  App Check: {os.getenv('APP_CHECK_ENABLED', 'false')}")
        print("\nPress Ctrl+C to stop the server")
        print("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer stopped")
