"""Stand-in for the customer's webhook endpoint. POST /hook records the request; GET /received lists them."""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

received = []


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        received.append({"headers": dict(self.headers), "body": body})
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        out = json.dumps(received).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
