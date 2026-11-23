#!/usr/bin/env python3
"""Add a weekly snapshot to data/followers.csv.

  python3 scripts/fetch_counts.py                     # fetch everything it can, today's date
  python3 scripts/fetch_counts.py --date 2026-11-30   # label the snapshot with another date
  python3 scripts/fetch_counts.py --set aoc.facebook=2310000@2026-11-29 --set harris.facebook=6300000
  python3 scripts/fetch_counts.py --dry-run           # print, don't write

Automatic sources (public, no login):
  YouTube    youtube.com/@<handle>                 subscribers, rounded by YouTube (marked approximate)
  X          api.fxtwitter.com/<handle>            exact count
  TikTok     tiktok.com/@<handle> embedded JSON    exact count
  Instagram  instastatistics.com/<handle>          third-party tracker, usually a few days old;
             falls back to Social Blade for accounts it does not track (1 credit)
  Facebook   the larger of Social Blade page likes (1 credit per page) and the latest hand-checked
             follower count in data/facebook_followers.csv
Social Blade credentials come from SOCIALBLADE_CLIENT_ID / SOCIALBLADE_TOKEN, or from network secrets
on the environment. Values passed with --set always win.
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
    """Instastatistics first (free); Social Blade (1 credit) for accounts it does not track."""
    try:
        res = fetch_instastatistics(handle, today)
        age = (dt.date.fromisoformat(today) - dt.date.fromisoformat(res[1])).days if res[1] else 99
        if age <= 7:
            return res
        print(f"  (instastatistics figure for {handle} is {age} days old, asking Social Blade)")
    except Exception:  # noqa: BLE001
        pass
    if True:
        data = socialblade("instagram", handle)
        daily = sorted(data.get("daily") or [], key=lambda r: r["date"])
        if daily:
            n, date = daily[-1]["followers"], daily[-1]["date"][:10]
        else:
            n, date = data["statistics"]["total"]["followers"], today
        return int(n), date, f"https://socialblade.com/instagram/user/{handle.lstrip('@').lower()}"


def fetch_instastatistics(handle, today):
    h = handle.lstrip("@")
    page = get(f"https://instastatistics.com/{h}")
    nums = re.findall(r"\b\d{1,3}(?:,\d{3})+\b", page)
    if not nums:
        raise ValueError("no follower figure found on tracker page")
    dates = sorted(set(re.findall(r"20\d\d-\d\d-\d\d", page)))
    count_date = dates[-1] if dates else None
    return int(nums[0].replace(",", "")), count_date, f"https://instastatistics.com/{h}"


def parse_compact(t):
    t = t.replace(",", "").strip()
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get(t[-1:].upper(), 1)
    return int(round(float(t.rstrip("KMBkmb")) * mult)), mult != 1


def fetch_youtube(handle, today):
    h = handle.lstrip("@")
    page = get(f"https://www.youtube.com/@{h}")
    m = re.search(r'"content":"([\d.,]+[KMB]?) subscribers?"', page) or re.search(r'"subscriberCountText":\{"simpleText":"([\d.,]+[KMB]?) subscribers?"', page)
    if not m:
        raise ValueError("subscriber count not found on channel page")
    n, rounded = parse_compact(m.group(1))
    return n, today, f"https://www.youtube.com/@{h}", rounded


def socialblade(platform, handle):
    """Social Blade Business API. Credentials: SOCIALBLADE_CLIENT_ID / SOCIALBLADE_TOKEN env vars, or
    network secrets injected by the environment's proxy. Each new lookup costs one credit."""
    import os, urllib.parse
    q = {"query": handle.lstrip("@")}
    if os.environ.get("SOCIALBLADE_CLIENT_ID"):
        q["clientid"] = os.environ["SOCIALBLADE_CLIENT_ID"]
    if os.environ.get("SOCIALBLADE_TOKEN"):
        q["token"] = os.environ["SOCIALBLADE_TOKEN"]
    d = json.loads(get(f"https://matrix.sbapis.com/b/{platform}/statistics?" + urllib.parse.urlencode(q), tries=2))
    if not d.get("status", {}).get("success"):
        raise ValueError(f"Social Blade: {d.get('status', {}).get('error', 'request failed')}")
    left = d.get("info", {}).get("credits", {}).get("available")
    if left is not None:
        CREDITS["left"] = left
    return d["data"]


CREDITS = {}


FB_FOLLOWERS = ROOT / "data/facebook_followers.csv"


def manual_fb_followers(cid):
    """Latest hand-checked Facebook follower count for a candidate, or None."""
    if not FB_FOLLOWERS.exists():
        return None
    rows = [r for r in csv.DictReader(open(FB_FOLLOWERS, newline="")) if r["candidate"].strip() == cid and r["followers"].strip()]
    if not rows:
        return None
    r = max(rows, key=lambda r: r["date"])
    return int(r["followers"].replace(",", "")), r["date"].strip(), (r.get("source") or "").strip()


def fetch_facebook(handle, today, cid=None):
    """Use the larger of Social Blade page likes (fresh) and the latest hand-checked follower count."""
    likes = None
    try:
        data = socialblade("facebook", handle)
        daily = sorted(data.get("daily") or [], key=lambda r: r["date"])
        if daily:
            likes = (int(daily[-1]["likes"]), daily[-1]["date"][:10])
        else:
            likes = (int(data["statistics"]["total"]["likes"]), today)
    except Exception as e:  # noqa: BLE001
        sb_error = e
    fol = manual_fb_followers(cid) if cid else None
    if fol and (not likes or fol[0] >= likes[0]):
        note = "Page followers, checked by hand" + ("" if likes else "; Social Blade has stopped crawling this page")
        return fol[0], fol[1], f"https://www.facebook.com/{handle.lstrip('@')}/", True, note
    if likes:
        return likes[0], likes[1], f"https://socialblade.com/facebook/page/{handle.lstrip('@').lower()}", False, "Page likes (Social Blade)"
    raise sb_error


FETCHERS = {"facebook": fetch_facebook, "x": fetch_x, "tiktok": fetch_tiktok, "instagram": fetch_instagram, "youtube": fetch_youtube}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="snapshot date, YYYY-MM-DD")
    ap.add_argument("--set", action="append", default=[], metavar="CAND.PLATFORM=N[@YYYY-MM-DD]",
                    help="manual value, e.g. aoc.facebook=2310000@2026-11-29 (date defaults to snapshot date)")
    ap.add_argument("--only", action="append", default=[], metavar="CAND", help="limit to these candidate ids")
    ap.add_argument("--platform", action="append", default=[], metavar="P", help="limit to these platform ids")
    ap.add_argument("--replace", action="store_true",
                    help="re-fetch and overwrite rows that already exist in the snapshot (use with --platform/--only)")
    ap.add_argument("--fill", action="store_true",
                    help="add only the rows missing from an existing snapshot (e.g. after adding a person or platform)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cfg = json.loads((ROOT / "data/candidates.json").read_text())
    rows = list(csv.DictReader(open(CSV, newline=""))) if CSV.exists() else []
    have = {(r["candidate"], r["platform"]) for r in rows if r["snapshot"] == a.date}
    original = list(rows)
    in_scope = lambda cid, pid: (not a.only or cid in a.only) and (not a.platform or pid in a.platform)
    if a.replace:
        rows = [r for r in rows if not (r["snapshot"] == a.date and in_scope(r["candidate"], r["platform"]))]
        have = {(r["candidate"], r["platform"]) for r in rows if r["snapshot"] == a.date}
        a.fill = True
    if have and not a.fill:
        sys.exit(f"A snapshot dated {a.date} already exists in {CSV.name}. Use --fill to add missing rows, "
                 "edit rows by hand, or pick another --date.")

    manual = {}
    for s in a.set:
        m = re.fullmatch(r"(\w+)\.(\w+)=([\d,]+)(?:@(\d{4}-\d\d-\d\d))?", s.strip())
        if not m:
            sys.exit(f"Bad --set value '{s}'. Use cand.platform=N or cand.platform=N@YYYY-MM-DD")
        manual[(m.group(1), m.group(2))] = (int(m.group(3).replace(",", "")), m.group(4) or a.date)

    last = {}
    for r in sorted(original, key=lambda r: r["snapshot"]):  # most recent row wins (incl. rows being replaced)
        last[(r["candidate"], r["platform"])] = r

    new, problems = [], []
    for c in cfg["candidates"]:
        if a.only and c["id"] not in a.only:
            continue
        for p in cfg["platforms"]:
            if a.platform and p["id"] not in a.platform:
                continue
            key = (c["id"], p["id"])
            acct = c["accounts"].get(p["id"], {})
            if acct.get("status") == "none" or key in have:
                continue
            if not acct.get("handle") and key not in manual:
                continue  # account not identified yet
            row = {"snapshot": a.date, "candidate": c["id"], "platform": p["id"], "approximate": "false", "note": ""}
            if key in manual:
                n, d = manual[key]
                row.update(followers=n, count_date=d, source="manual entry")
            elif p["id"] in FETCHERS:
                try:
                    kw = {"cid": c["id"]} if p["id"] == "facebook" else {}
                    n, d, src, *rest = FETCHERS[p["id"]](acct["handle"], a.date, **kw)
                    row.update(followers=n, count_date=d or "", source=src,
                               approximate="true" if (rest and rest[0]) else "false",
                               note=rest[1] if len(rest) > 1 else "")
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
    if CREDITS:
        print(f"\nSocial Blade credits left: {CREDITS['left']}")
    if a.dry_run:
        print("\n(dry run, nothing written)")
        return
    with open(CSV, "w", newline="") as f:  # rewrite so --replace drops the old rows
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in FIELDS} for r in rows] + new)
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
