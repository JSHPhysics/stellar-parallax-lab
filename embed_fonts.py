#!/usr/bin/env python3
"""
embed_fonts.py — produce fonts_inline.css with woff2 fonts as base64 data URIs.

USAGE:
    python embed_fonts.py          # writes fonts_inline.css

Fetches the Google Fonts CSS (with a modern User-Agent to get woff2), downloads
every referenced .woff2 file, and rewrites each `url(...)` as a base64 data URI.
The resulting fonts_inline.css is then consumed by build_html.py so the final
parallax-lab.html runs with **zero external requests**.

Run this once per font-set change.  Output is checked in to source control
so re-builds don't need network access.
"""
import base64
import re
from pathlib import Path
import urllib.request

CSS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600"
    "&family=JetBrains+Mono:wght@400;500"
    "&family=Public+Sans:wght@400;500;600"
    "&display=swap"
)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    print(f"fetching CSS {CSS_URL}")
    css = fetch(CSS_URL).decode("utf-8")
    # Keep only latin subsets (smaller) — filter out font-face blocks for other subsets
    # Google prefixes each @font-face with a /* subset */ comment
    blocks = re.findall(r"(/\*[^*]*\*/\s*@font-face\s*\{[^}]*\})", css, re.DOTALL)
    kept = []
    for blk in blocks:
        subset_match = re.match(r"/\*\s*(\S+)\s*\*/", blk)
        subset = subset_match.group(1) if subset_match else "?"
        if subset != "latin":
            continue
        kept.append(blk)
    if not kept:
        # Fallback: keep everything
        kept = blocks or [css]
    print(f"  kept {len(kept)} font-face blocks (latin subset)")

    url_re = re.compile(r"url\((https://[^)]+\.woff2)\)")
    out_blocks = []
    total_bytes = 0
    for blk in kept:
        urls = url_re.findall(blk)
        for u in urls:
            print(f"  fetching {u}")
            data = fetch(u)
            total_bytes += len(data)
            b64 = base64.b64encode(data).decode("ascii")
            data_uri = f"url(data:font/woff2;base64,{b64})"
            blk = blk.replace(f"url({u})", data_uri)
        out_blocks.append(blk)

    out = "\n".join(out_blocks)
    Path("fonts_inline.css").write_text(out, encoding="utf-8")
    print(f"wrote fonts_inline.css ({total_bytes/1024:.1f} KB of fonts, "
          f"{len(out)/1024:.1f} KB CSS with base64)")


if __name__ == "__main__":
    main()
