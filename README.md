# 2028 Social Tracker

A Chaotic Era dashboard tracking social media followings of potential 2028 Democratic presidential
candidates on X, TikTok, Facebook and Instagram, one snapshot per week.

Live dashboard (Artifact): https://claude.ai/artifact/2fFdChcBnZH9bSjYkD2EzD

## Layout

| Path | What it is |
|---|---|
| `data/candidates.json` | Who is tracked: names, roles, chart color slot, and the account handle on each platform |
| `data/followers.csv` | Every weekly count, one row per person × platform × snapshot, with its source |
| `src/template.html` | The dashboard page (styles + script); data is injected at build time |
| `scripts/fetch_counts.py` | Fetches this week's counts and appends a snapshot to the CSV |
| `scripts/build.py` | Builds `dist/index.html`, the single file published as the Artifact |

## Weekly update

```bash
python3 scripts/fetch_counts.py                      # all five platforms fetched automatically
python3 scripts/build.py
```

Then republish `dist/index.html` to the Artifact URL above (ask Claude: "republish the 2028 social
tracker"), and commit.

**Facebook** hides follower counts from logged-out visitors, so it is not fetched. Look the numbers up
while logged in and pass them in, or the previous figure is carried forward and tagged as dated on the page:

```bash
python3 scripts/fetch_counts.py --set aoc.facebook=2310000 --set newsom.facebook=2400000@2026-11-28
```

`--dry-run` prints what would be written. Any fetch that fails is carried forward and listed under
"Needs attention". To correct a number by hand, edit its row in `data/followers.csv` and rebuild.

## Adding a candidate

Add an entry to `data/candidates.json` with their handle on each platform, then run
`python3 scripts/fetch_counts.py --date <latest snapshot date> --fill` to backfill them. Use `"status": "none"` for a platform where they have no account.


## Sources

- X: `api.fxtwitter.com/<handle>` (public mirror of the X profile, exact count)
- TikTok: the `followerCount` embedded in the public profile page (exact count)
- YouTube: the channel page header (rounded by YouTube, marked approximate)
- Instagram: instastatistics.com when it tracks the account and is at most 7 days behind (free); otherwise Social Blade (1 credit)
- Facebook: Social Blade Business API (page likes, dated daily; 1 credit per page). Pages Social Blade has stopped crawling (AOC, Shapiro, Khanna, Moore) need `--set`. Credentials come from the `SOCIALBLADE_CLIENT_ID` and `SOCIALBLADE_TOKEN` environment variables on the 2028socialtracker cloud environment. Never commit them.

## Automatic weekly update

A scheduled Claude task runs every Monday at 7:40am Eastern on the `2028socialtracker` cloud environment.
It runs `fetch_counts.py` and `build.py`, commits, pushes, and republishes the Artifact, then sends a push
notification with the top five, the biggest weekly gains, anything it could not refresh, and Social Blade
credits left. A normal week uses about 25–30 credits.
