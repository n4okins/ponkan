import os
from http.server import ThreadingHTTPServer

from ponkan.api import Handler
from ponkan.db import init_db

HOST = os.environ.get("PONKAN_HOST", "0.0.0.0")
PORT = int(os.environ.get("PONKAN_PORT", "8080"))

if __name__ == "__main__":
    init_db()
    print(f"Ponkan 2.0 listening on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
