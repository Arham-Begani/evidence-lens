"""Check the public preview on a temporary loopback server, then stop it."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import uuid

from check_desk_browser import run

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / '.test-runs' / ('browser-' + uuid.uuid4().hex)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT / 'site')))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        run(f'http://127.0.0.1:{server.server_port}/desk/index.html', output)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == '__main__':
    main()
