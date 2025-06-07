import base64
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler

USERNAME = os.environ.get("BASIC_AUTH_USERNAME", "admin")
PASSWORD = os.environ.get("BASIC_AUTH_PASSWORD", "demo")

# Precompute the valid Authorization header value
VALID_TOKEN = "Basic " + base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()

class AuthHandler(SimpleHTTPRequestHandler):
    def do_HEAD(self):
        if not self._check_auth():
            return
        super().do_HEAD()

    def do_GET(self):
        if not self._check_auth():
            return
        super().do_GET()

    def _check_auth(self):
        auth = self.headers.get("Authorization")
        if auth == VALID_TOKEN:
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="React Frontend"')
        self.end_headers()
        return False

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("", port), AuthHandler)
    print(f"Serving on port {port} with basic auth")
    server.serve_forever()
