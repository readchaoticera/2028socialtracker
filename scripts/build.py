#!/usr/bin/env python3
"""Build the dashboard: data/candidates.json + data/followers.csv + src/template.html -> dist/index.html.

The output is a single self-contained HTML file (data and logo inlined), ready to publish as an Artifact.
"""
import base64, csv, json, sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
    html = (ROOT / "src/template.html").read_text()
    logo = "data:image/png;base64," + base64.b64encode((ROOT / "assets/chaotic-era-logo.png").read_bytes()).decode()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    assert "/*__DATA__*/null" in html and "__LOGO__" in html
    html = html.replace("/*__DATA__*/null", payload).replace("__LOGO__", logo)
    out = ROOT / "dist/index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html)
    latest = data["snapshots"][-1]
    print(f"Built {out.relative_to(ROOT)}: {len(data['snapshots'])} snapshot(s), latest {latest['date']}, "
          f"{len(data['candidates'])} candidates x {len(data['platforms'])} platforms")


if __name__ == "__main__":
    main()
