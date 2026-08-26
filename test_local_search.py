"""Assert the contract SillyTavern actually relies on.

The extension does not consume JSON. It runs four CSS selectors over whatever
HTML comes back, so "the server returned 200" proves nothing -- a page with the
wrong class names is a silent zero-results bug. These checks parse the real
response the same way the extension does.

Run:  python test_local_search.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = 18899  # deliberately not 18888, so a running instance is not disturbed
BASE = "http://127.0.0.1:%d" % PORT


def get(path: str, timeout: int = 60) -> str:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as response:
        return response.read().decode("utf-8")


def wait_until_up(proc: subprocess.Popen, tries: int = 30) -> None:
    for _ in range(tries):
        if proc.poll() is not None:
            raise AssertionError("server exited early with code %s" % proc.returncode)
        try:
            get("/", timeout=2)
            return
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    raise AssertionError("server did not come up on %s" % BASE)


def check(name: str, condition: bool, detail: str = "") -> bool:
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name, ("  -- " + detail) if detail and not condition else ""))
    return condition


def main() -> int:
    proc = subprocess.Popen(
        [sys.executable, "local_search.py", "--port", str(PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    ok = True
    try:
        wait_until_up(proc)

        # 1. SillyTavern GETs the base URL first and requires it to succeed.
        base = get("/")
        ok &= check("base page serves and carries #urls", 'id="urls"' in base)

        # 2. It then looks for href="(/client.+\.css)". ".+" needs at least one
        #    character between "client" and ".css" -- "/client.css" would NOT
        #    match, which is why the served name is longer than that.
        match = re.search(r'href="(/client.+\.css)"', base)
        ok &= check("client css href matches SillyTavern's regex", bool(match),
                    "no href in the base page satisfies /client.+\\.css")
        if match:
            css = get(match.group(1))
            ok &= check("that css path actually serves", isinstance(css, str))

        # 3. The four selectors the extension runs over search results.
        html = get("/search?q=rust+programming+language", timeout=90)
        urls_block = re.search(r'<div id="urls">(.*)</div>', html, re.S)
        ok &= check("search response has the #urls container", bool(urls_block))
        inner = urls_block.group(1) if urls_block else ""

        links = re.findall(r'class="url_(?:wrapper|header)"[^>]*href="([^"]+)"', inner)
        snippets = re.findall(r'<p class="content">(.*?)</p>', inner, re.S)
        ok &= check("links carry .url_wrapper/.url_header with href", bool(links),
                    "0 links -- the extension would report no results")
        ok &= check("snippets carry p.content", bool(snippets))
        ok &= check("every link is absolute", all(l.startswith("http") for l in links),
                    "relative hrefs resolve against SillyTavern, not the source")

        # 4. Images use data-src, not src. Getting this wrong is invisible
        #    because text search keeps working.
        images = get("/search?q=red+fox&categories=images", timeout=90)
        img_srcs = re.findall(r'<img[^>]*data-src="([^"]+)"', images)
        ok &= check("image results use data-src", bool(img_srcs),
                    "0 images -- check the attribute name, not just the query")

        # 5. An empty query must not 500; the extension has no error path.
        empty = get("/search?q=")
        ok &= check("empty query returns a valid empty page", 'id="urls"' in empty)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print("\n%s" % ("all checks passed" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
