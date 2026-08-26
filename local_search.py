"""A local, keyless search endpoint that SillyTavern already knows how to read.

SillyTavern's Web Search extension has no free backend. Of its sources, SerpApi,
Tavily, Serper and Z.AI all want an API key, KoboldCpp wants a KoboldCpp, and
SearXNG wants an instance URL. Public SearXNG instances were measured from this
machine and are not usable: searx.be answers a captcha page, and the ones that
do not are returning HTTP 429.

So this serves the SearXNG *shape* from DuckDuckGo results, locally, with no
account anywhere. Point the extension's SearXNG URL at this process.

The contract is narrow and comes from reading the extension, not from guessing.
Extension-WebSearch 1.2.0 parses exactly:

    #urls p.content                          -> result snippets
    #urls .url_header, #urls .url_wrapper    -> result links (href)
    .infobox p / .infobox a                  -> optional infobox (not emitted)
    #urls .detail img[data-src]              -> image results

SillyTavern's server also GETs the base URL first and, if it finds
href="/client*.css", fetches that too. Both are answered below so the flow
matches what the server expects.

Run:
    python local_search.py [--port 18888] [--host 127.0.0.1]

Binds to loopback by default. There is no auth, so do not expose it.
"""

from __future__ import annotations

import argparse
import html
import logging
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - the message is the whole point
    sys.exit("ddgs is not installed. Run:  python -m pip install ddgs")

MAX_RESULTS = 10
MAX_IMAGES = 10

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>local-search</title>
<link rel="stylesheet" href="/client.local.css"></head>
<body><div id="urls">{body}</div></body></html>"""


def _text_results(query: str) -> str:
    rows = []
    for item in DDGS().text(query, max_results=MAX_RESULTS):
        href = item.get("href") or ""
        title = item.get("title") or ""
        snippet = item.get("body") or ""
        if not href:
            continue
        rows.append(
            '<article class="result">'
            '<a class="url_wrapper" href="{href}">{title}</a>'
            '<p class="content">{snippet}</p>'
            "</article>".format(
                href=html.escape(href, quote=True),
                title=html.escape(title),
                snippet=html.escape(snippet),
            )
        )
    return "\n".join(rows)


def _image_results(query: str) -> str:
    rows = []
    for item in DDGS().images(query, max_results=MAX_IMAGES):
        src = item.get("image") or ""
        if not src:
            continue
        # data-src, not src: that is the attribute the extension reads.
        rows.append(
            '<div class="detail"><img data-src="{src}"></div>'.format(
                src=html.escape(src, quote=True)
            )
        )
    return "\n".join(rows)


class Handler(BaseHTTPRequestHandler):
    server_version = "local-search/1.0"

    def _send(self, body: str, status: int = 200, ctype: str = "text/html; charset=utf-8") -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        parsed = urlparse(self.path)

        if parsed.path == "/client.local.css":
            self._send("/* intentionally empty */", ctype="text/css")
            return

        if parsed.path != "/search":
            # The base page. SillyTavern fetches this before searching.
            self._send(PAGE.format(body=""))
            return

        params = parse_qs(parsed.query)
        query = (params.get("q") or [""])[0].strip()
        categories = (params.get("categories") or [""])[0].strip().lower()

        if not query:
            self._send(PAGE.format(body=""))
            return

        try:
            body = _image_results(query) if categories == "images" else _text_results(query)
        except Exception as exc:  # a dead upstream must not 500 the extension
            logging.warning("search failed for %r: %s", query, exc)
            body = ""

        self._send(PAGE.format(body=body))

    def log_message(self, fmt: str, *args) -> None:
        logging.info("%s - %s", self.address_string(), fmt % args)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=18888)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    logging.info("local search on http://%s:%d  (SearXNG-shaped, DuckDuckGo-backed)",
                 args.host, args.port)
    logging.info("point SillyTavern's Web Search -> SearXNG URL at that address")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
