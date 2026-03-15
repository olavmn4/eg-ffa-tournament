"""
fetch_tournament_matches.py

Fetches all tournament matches by querying recent matches for every player
who participated, filtering for match IDs starting with "m72".

Usage:
    python scripts/fetch_tournament_matches.py [--workers 5] [--count 40]

Output:
    scripts/tournament_matches.json  — deduplicated dict of match_id -> match data
"""

import json
import time
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

MATCH_PREFIX = "m72"
BASE_URL = "https://mcsrranked.com/api/users/{username}/matches?count={count}&type=3"


def fetch_matches(username, count=40):
    url = BASE_URL.format(username=username, count=count)
    try:
        req = Request(url, headers={"User-Agent": "tournament-stats/1.0"})
        with urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("status") != "success":
            return username, []
        return username, data.get("data", [])
    except (URLError, HTTPError, json.JSONDecodeError, Exception):
        return username, None  # None = error, retry candidate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--count", type=int, default=40,
                        help="matches to fetch per player (default 40, max ~100)")
    args = parser.parse_args()

    # Load player list
    players_path = "scripts/tournament_players.json"
    try:
        with open(players_path) as f:
            players = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {players_path} not found. Run from repo root.")
        sys.exit(1)

    print(f"Querying {len(players)} players with {args.workers} workers, count={args.count}")

    # Load existing progress if any
    out_path = "scripts/tournament_matches.json"
    try:
        with open(out_path) as f:
            matches = json.load(f)
        print(f"Resuming — {len(matches)} matches already collected")
    except FileNotFoundError:
        matches = {}

    # Track which players returned errors for retry
    errors = []
    done = 0
    found_new = 0

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(fetch_matches, p, args.count): p for p in players}
        for future in as_completed(futures):
            username, result = future.result()
            done += 1

            if result is None:
                errors.append(username)
            else:
                for m in result:
                    mid = m.get("seed", {}).get("id", "")
                    if not mid.startswith(MATCH_PREFIX):
                        continue
                    if mid not in matches:
                        matches[mid] = m
                        found_new += 1

            if done % 50 == 0 or done == len(players):
                print(f"  {done}/{len(players)} players queried — "
                      f"{len(matches)} tournament matches found (+{found_new} new), "
                      f"{len(errors)} errors")
                with open(out_path, "w") as f:
                    json.dump(matches, f, indent=2)
                found_new = 0

            # Simple rate limiting
            time.sleep(0.05)

    # Retry errors once
    if errors:
        print(f"\nRetrying {len(errors)} errored players...")
        time.sleep(5)
        for username in errors:
            _, result = fetch_matches(username, args.count)
            if result:
                for m in result:
                    mid = m.get("seed", {}).get("id", "")
                    if mid.startswith(MATCH_PREFIX):
                        if mid not in matches:
                            matches[mid] = m
            time.sleep(0.1)

    # Final save
    with open(out_path, "w") as f:
        json.dump(matches, f, indent=2)

    print(f"\nDone. {len(matches)} unique tournament matches saved to {out_path}")
    if errors:
        print(f"  {len(errors)} players still failed after retry — "
              f"re-run to pick them up")


if __name__ == "__main__":
    main()
