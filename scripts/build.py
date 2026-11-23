#!/usr/bin/env python3
"""Build the dashboard: data/candidates.json + data/followers.csv + src/template.html -> dist/index.html.

The output is a single self-contained HTML file (data and logo inlined), ready to publish as an Artifact.
"""
import base64, csv, json, sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EMBED_PATH = "embed-k7q2m9"  # docs/<EMBED_PATH>/ is the iframe source for the paywalled beehiiv post


def load():
    cfg = json.loads((ROOT / "data/candidates.json").read_text())
    pids = {p["id"] for p in cfg["platforms"]}
    cids = {c["id"] for c in cfg["candidates"]}
    snaps = OrderedDict()
    with open(ROOT / "data/followers.csv", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            cid, pid = row["candidate"].strip(), row["platform"].strip()
            if cid not in cids:
                sys.exit(f"followers.csv line {i}: unknown candidate '{cid}' (add it to data/candidates.json)")
            if pid not in pids:
                sys.exit(f"followers.csv line {i}: unknown platform '{pid}'")
            raw = row["followers"].strip().replace(",", "")
            followers = int(raw) if raw else None
            snaps.setdefault(row["snapshot"].strip(), {}).setdefault(cid, {})[pid] = {
                "followers": followers,
                "approximate": row.get("approximate", "").strip().lower() in ("true", "1", "yes"),
                "count_date": row.get("count_date", "").strip() or None,
                "source": row.get("source", "").strip() or None,
                "note": row.get("note", "").strip() or None,
            }
    if not snaps:
        sys.exit("followers.csv has no rows")
    snapshots = [{"date": d, "counts": snaps[d]} for d in sorted(snaps)]
    return {**cfg, "snapshots": snapshots}


def main():
    data = load()
    for c in data["candidates"]:  # embed profile pictures so the page makes no external image requests
        pic = ROOT / f"assets/avatars/{c['id']}.jpg"
        if pic.exists():
            c["avatar"] = "data:image/jpeg;base64," + base64.b64encode(pic.read_bytes()).decode()
    html = (ROOT / "src/template.html").read_text()
    logo = "data:image/png;base64," + base64.b64encode((ROOT / "assets/chaotic-era-logo.png").read_bytes()).decode()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    assert "/*__DATA__*/null" in html and "__LOGO__" in html
    html = html.replace("/*__DATA__*/null", payload).replace("__LOGO__", logo)
    out = ROOT / "dist/index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html)  # Artifact version: the Artifact host adds the document skeleton

    # GitHub Pages version: a complete standalone document in docs/
    desc = ("Weekly follower counts on X, TikTok, Facebook, Instagram, YouTube, Threads and Bluesky for the likely "
            "2028 Democratic and Republican presidential contenders. From Chaotic Era.")
    head = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        f'<meta name="description" content="{desc}">\n'
        '<meta property="og:type" content="website">\n'
        '<meta property="og:title" content="2028 Social Tracker · Chaotic Era">\n'
        f'<meta property="og:description" content="{desc}">\n'
        '<meta name="twitter:card" content="summary">\n'
        '<style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n'
        '</head>\n<body>\n'
    )
    pages = ROOT / "docs/index.html"
    pages.parent.mkdir(exist_ok=True)
    pages.write_text(head + html + "\n</body>\n</html>\n")
    (ROOT / "docs/.nojekyll").write_text("")

    # Embed version for an iframe inside a paywalled beehiiv post: no masthead, subscribe bar or footer
    # (the post supplies those), not indexed by search engines, at a hard-to-guess path.
    import re as _re
    emb = html
    for pat in (r'<header class="masthead">.*?</header>', r'<aside class="cta".*?</aside>', r'<footer class="site-footer">.*?</footer>'):
        emb, n = _re.subn(pat, "", emb, count=1, flags=_re.S)
        assert n == 1, f"embed build: pattern not found: {pat}"
    emb_head = head.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n<meta name="robots" content="noindex, nofollow">')
    emb_dir = ROOT / f"docs/{EMBED_PATH}"
    emb_dir.mkdir(parents=True, exist_ok=True)
    (emb_dir / "index.html").write_text(emb_head + emb + "\n</body>\n</html>\n")
    latest = data["snapshots"][-1]
    print(f"Built {out.relative_to(ROOT)}: {len(data['snapshots'])} snapshot(s), latest {latest['date']}, "
          f"{len(data['candidates'])} candidates x {len(data['platforms'])} platforms")


if __name__ == "__main__":
    main()
