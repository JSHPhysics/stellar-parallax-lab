#!/usr/bin/env python3
"""
build_html.py — inject manifest.json into parallax-lab.template.html.

USAGE:
    python build_html.py                # template -> parallax-lab.html
    python build_html.py --check        # also print final file size

Replaces the literal token:
    /* __MANIFEST_JSON__ */ {"stars": []}
in the template with the contents of manifest.json.  Run after every
invocation of prepare_images.py.
"""
import argparse
import json
from pathlib import Path

TEMPLATE = Path("parallax-lab.template.html")
MANIFEST = Path("manifest.json")
FONTS    = Path("fonts_inline.css")
OUTPUT   = Path("parallax-lab.html")
MANIFEST_PLACEHOLDER = '/* __MANIFEST_JSON__ */ {"stars": []}'
FONTS_PLACEHOLDER = '/* __FONTS_CSS__ */'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="print size stats")
    ap.add_argument("--template", default=str(TEMPLATE))
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--fonts", default=str(FONTS))
    ap.add_argument("--out", default=str(OUTPUT))
    args = ap.parse_args()

    tpl_text = Path(args.template).read_text(encoding="utf-8")
    if MANIFEST_PLACEHOLDER not in tpl_text:
        raise SystemExit(
            f"Manifest placeholder not found in {args.template}: {MANIFEST_PLACEHOLDER!r}"
        )
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    # Inject as a plain JS object literal (json is a valid JS expression).
    replacement = json.dumps(manifest, separators=(",", ":"))
    out_text = tpl_text.replace(MANIFEST_PLACEHOLDER, replacement, 1)

    # Optional: inline fonts CSS (for fully offline operation)
    if FONTS_PLACEHOLDER in out_text:
        fpath = Path(args.fonts)
        if fpath.exists():
            fonts_css = fpath.read_text(encoding="utf-8")
            out_text = out_text.replace(FONTS_PLACEHOLDER, fonts_css, 1)
            print(f"  inlined {fpath} ({len(fonts_css)/1024:.1f} KB)")
        else:
            print(f"  WARN: {fpath} not found; skipping font embed — "
                  "run embed_fonts.py first for fully-offline HTML")

    Path(args.out).write_text(out_text, encoding="utf-8")

    sz_kb = Path(args.out).stat().st_size / 1024
    print(f"wrote {args.out}  ({sz_kb/1024:.2f} MB, {sz_kb:.1f} KB)")
    if args.check:
        n_stars = len(manifest["stars"])
        img_bytes = sum(s["image_bytes"] for s in manifest["stars"])
        print(f"  scenarios: {n_stars}")
        print(f"  embedded images: {img_bytes/1024/1024:.2f} MB")
        if sz_kb > 12 * 1024:
            print(f"  WARNING: exceeds 12 MB target")


if __name__ == "__main__":
    main()
