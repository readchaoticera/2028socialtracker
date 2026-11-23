#!/usr/bin/env python3
"""Add a weekly snapshot to data/followers.csv.

  python3 scripts/fetch_counts.py                     # fetch everything it can, today's date
  python3 scripts/fetch_counts.py --date 2026-11-30   # label the snapshot with another date
  python3 scripts/fetch_counts.py --set aoc.facebook=2310000@2026-11-29 --set harris.facebook=6300000
  python3 scripts/fetch_counts.py --dry-run           # print, don't write

Automatic sources (public, no login):
  X          api.fxtwitter.com/<handle>            exact count
  TikTok     tiktok.com/@<handle> embedded JSON    exact count
  Instagram  instastatistics.com/<handle>          third-party tracker, usually a few days old
Facebook hides counts from logged-out visitors, so it is never fetched: pass it with --set,
or the previous figure is carried forward with its original date (the dashboard tags it as dated).
Any fetch that fails is carried forward the same way and reported at the end.
"""
import argparse, csv, datetime as dt, json, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data/followers.csv"
FIELDS = ["snapshot", "candidate", "platform", "followers", "approximate", "count_date", "source", "note"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def get(url, tries=4):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001  (these public endpoints fail intermittently)
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def fetch_x(handle, today):
    h = handle.lstrip("@")
    d = json.loads(get(f"https://api.fxtwitter.com/{h}"))
    n = d["user"]["followers"]
    return int(n), today, f"https://api.fxtwitter.com/{h}"


def fetch_tiktok(handle, today):
    h = handle.lstrip("@")
    page = get(f"https://www.tiktok.com/@{h}")
    m = re.search(r'"statsV2":\{[^}]*?"followerCount":"(\d+)"', page) or re.search(r'"followerCount":"(\d+)"', page)
    if not m:
        m = re.search(r'"followerCount":(\d+)', page)
    if not m:
        raise ValueError("followerCount not found in page")
    return int(m.group(1)), today, f"https://www.tiktok.com/@{h}"


def fetch_instagram(handle, today):
    h = handle.lstrip("@")
    page = get(f"https://instastatistics.com/{h}")
    nums = re.findall(r"\b\d{1,3}(?:,\d{3})+\b", page)
    if not nums:
        raise ValueError("no follower figure found on tracker page")
    dates = sorted(set(re.findall(r"20\d\d-\d\d-\d\d", page)))
    count_date = dates[-1] if dates else None
    return int(nums[0].replace(",", "")), count_date, f"https://instastatistics.com/{h}"


FETCHERS = {"x": fetch_x, "tiktok": fetch_tiktok, "instagram": fetch_instagram}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="snapshot date, YYYY-MM-DD")
    ap.add_argument("--set", action="append", default=[], metavar="CAND.PLATFORM=N[@YYYY-MM-DD]",
                    help="manual value, e.g. aoc.facebook=2310000@2026-11-29 (date defaults to snapshot date)")
    ap.add_argument("--only", action="append", default=[], metavar="CAND", help="limit to these candidate ids")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cfg = json.loads((ROOT / "data/candidates.json").read_text())
    rows = list(csv.DictReader(open(CSV, newline=""))) if CSV.exists() else []
    if any(r["snapshot"] == a.date for r in rows):
        sys.exit(f"A snapshot dated {a.date} already exists in {CSV.name}. Edit those rows by hand or pick another --date.")

    manual = {}
    for s in a.set:
        m = re.fullmatch(r"(\w+)\.(\w+)=([\d,]+)(?:@(\d{4}-\d\d-\d\d))?", s.strip())
        if not m:
            sys.exit(f"Bad --set value '{s}'. Use cand.platform=N or cand.platform=N@YYYY-MM-DD")
        manual[(m.group(1), m.group(2))] = (int(m.group(3).replace(",", "")), m.group(4) or a.date)

    last = {}
    for r in rows:  # most recent row wins
        last[(r["candidate"], r["platform"])] = r

    new, problems = [], []
    for c in cfg["candidates"]:
        if a.only and c["id"] not in a.only:
            continue
        for p in cfg["platforms"]:
            key = (c["id"], p["id"])
            acct = c["accounts"].get(p["id"], {})
            if acct.get("status") == "none":
                continue
            row = {"snapshot": a.date, "candidate": c["id"], "platform": p["id"], "approximate": "false", "note": ""}
            if key in manual:
                n, d = manual[key]
                row.update(followers=n, count_date=d, source="manual entry")
            elif p["id"] in FETCHERS:
                try:
                    n, d, src = FETCHERS[p["id"]](acct["handle"], a.date)
                    row.update(followers=n, count_date=d or "", source=src)
                except Exception as e:  # noqa: BLE001
                    problems.append(f"{c['id']}.{p['id']}: {e}")
                    row = carry(row, last.get(key), problems, key)
            else:
                row = carry(row, last.get(key), problems, key)
            if row:
                new.append(row)
                prev = last.get(key)
                diff = ""
                if prev and prev.get("followers"):
                    diff = f"  ({int(row['followers']) - int(prev['followers']):+,})"
                print(f"{c['id']:>8} {p['id']:<10} {int(row['followers']):>12,}  {row['count_date'] or 'date unknown'}{diff}")

    if problems:
        print("\nNeeds attention:", *problems, sep="\n  ")
    if a.dry_run:
        print("\n(dry run, nothing written)")
        return
    with open(CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not rows:
            w.writeheader()
        w.writerows(new)
    print(f"\nAppended {len(new)} rows for {a.date} to {CSV.relative_to(ROOT)}. Next: python3 scripts/build.py")


def carry(row, prev, problems, key):
    if not prev or not prev.get("followers"):
        problems.append(f"{key[0]}.{key[1]}: no earlier figure to carry forward, row skipped")
        return None
    problems.append(f"{key[0]}.{key[1]}: carried forward {int(prev['followers']):,} from {prev['count_date'] or 'unknown date'}")
    row.update(followers=prev["followers"], approximate=prev.get("approximate", "false"),
               count_date=prev.get("count_date", ""), source=prev.get("source", ""),
               note=("Carried forward. " + (prev.get("note") or "")).strip())
    return row


if __name__ == "__main__":
    main()
