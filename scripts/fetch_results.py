#!/usr/bin/env python3
"""
Fetches tournament match results from the MCSR Ranked API.
Uses concurrent workers for speed while staying under the 500 req/10min rate limit.

For each matchup:
  1. Fetch p1's most recent match
  2. Validate: type==3, both players present, result exists
  3. If invalid → fallback fetch p2
  4. If still invalid → flag for manual review

Usage:
  python3 fetch_results.py --round 1
  python3 fetch_results.py --round 2
  python3 fetch_results.py --round 1 --dry-run
  python3 fetch_results.py --round 1 --workers 8   (default: 5)

Files:
  scripts/r1_matchups.json    — static R1 bracket matchups
  results.json                — confirmed results, keyed by "rX-matchIndex"
  scripts/pending_review.json — matches needing manual resolution
"""

import json
import time
import argparse
import urllib.request
import urllib.error
import os
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
R1_FILE      = os.path.join(SCRIPT_DIR, 'r1_matchups.json')
RESULTS_FILE = os.path.join(SCRIPT_DIR, '..', 'results.json')
PENDING_FILE = os.path.join(SCRIPT_DIR, 'pending_review.json')
API_BASE     = 'https://mcsrranked.com/api/users/'
PRIVATE_ROOM = 3

# Rate limiter: 480 req/10min (headroom below 500 hard limit)
MAX_REQUESTS_PER_10MIN = 480
WINDOW_SECONDS = 600

_rate_lock = threading.Lock()
_request_times = []
_print_lock = threading.Lock()


def tprint(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)


def rate_limited_sleep():
    """Block until we are safely under the rate limit."""
    with _rate_lock:
        now = time.time()
        cutoff = now - WINDOW_SECONDS
        while _request_times and _request_times[0] < cutoff:
            _request_times.pop(0)
        if len(_request_times) >= MAX_REQUESTS_PER_10MIN:
            sleep_for = _request_times[0] - cutoff + 0.1
            time.sleep(max(0, sleep_for))
            now = time.time()
            cutoff = now - WINDOW_SECONDS
            while _request_times and _request_times[0] < cutoff:
                _request_times.pop(0)
        _request_times.append(time.time())


def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception:
            pass
    return default


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def fetch_latest_match(username, attempt=0):
    """Fetch the most recent match for a username. Returns raw match dict or None."""
    rate_limited_sleep()
    url = API_BASE + username + '/matches?count=1'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'EG-FFA-Tournament/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        matches = data.get('data', [])
        return matches[0] if matches else None
    except urllib.error.HTTPError as e:
        if e.code == 429:
            if attempt < 3:
                tprint(f"  [RATE LIMITED] {username} — waiting 30s...")
                time.sleep(30)
                return fetch_latest_match(username, attempt + 1)
            return None
        if e.code == 404:
            return None
        tprint(f"  [HTTP {e.code}] {username}")
        return None
    except Exception as e:
        tprint(f"  [ERROR] {username}: {e}")
        return None


def validate_match(match, p1_username, p2_username):
    """Returns result dict if match is valid for this matchup, else None."""
    if not match:
        return None
    if match.get('type') != PRIVATE_ROOM:
        return None

    players = match.get('players', [])
    nicknames = {p['nickname'].lower() for p in players}

    if p1_username.lower() not in nicknames:
        return None
    if p2_username.lower() not in nicknames:
        return None

    result = match.get('result')
    if not result or not result.get('uuid'):
        return None  # tie or incomplete

    winner_uuid = result['uuid']
    winner_nick = next((p['nickname'] for p in players if p['uuid'] == winner_uuid), None)
    if not winner_nick:
        return None

    if winner_nick.lower() == p1_username.lower():
        winner, loser = p1_username, p2_username
    elif winner_nick.lower() == p2_username.lower():
        winner, loser = p2_username, p1_username
    else:
        return None

    return {
        'winner':    winner,
        'loser':     loser,
        'time_ms':   result.get('time'),
        'match_id':  match.get('id'),
        'date':      match.get('date'),
        'forfeited': match.get('forfeited', False),
    }


def process_matchup(round_num, m, results_snapshot):
    """Process one matchup in a worker thread. Returns (key, result_or_none, status_str)."""
    key = f'r{round_num}-{m["match_index"]}'
    p1, p2 = m['p1'], m['p2']

    if key in results_snapshot:
        return key, results_snapshot[key], 'skipped'

    # Fetch p1 first
    match = fetch_latest_match(p1)
    result = validate_match(match, p1, p2)
    fallback_used = False

    # Fallback to p2 if p1 miss
    if not result:
        match = fetch_latest_match(p2)
        result = validate_match(match, p1, p2)
        fallback_used = True

    if result:
        parts = [f"✓ {result['winner']} beats {result['loser']}"]
        if result['time_ms']:
            parts.append(f"in {result['time_ms']//1000}s")
        if result['forfeited']:
            parts.append('[forfeit]')
        if fallback_used:
            parts.append('(via p2)')
        return key, result, ' '.join(parts)
    else:
        return key, None, '⚠  flagged'


def build_round_matchups(round_num, r1_matchups, results):
    if round_num == 1:
        return [
            {
                'match_index': m['match_index'],
                'p1': m['p1'],
                'p2': m['p2'],
                'p1_seed': m.get('p1_seed'),
                'p2_seed': m.get('p2_seed'),
            }
            for m in r1_matchups
        ]

    prev_prefix = f'r{round_num - 1}-'
    prev = sorted(
        ((k, v) for k, v in results.items() if k.startswith(prev_prefix)),
        key=lambda kv: int(kv[0].split('-')[1])
    )

    matchups = []
    for i in range(0, len(prev), 2):
        if i + 1 >= len(prev):
            break
        _, m1 = prev[i]
        _, m2 = prev[i + 1]
        if not m1.get('winner') or not m2.get('winner'):
            continue
        matchups.append({'match_index': i // 2, 'p1': m1['winner'], 'p2': m2['winner']})

    return matchups


def process_round(round_num, matchups, results, pending, num_workers):
    to_fetch = [m for m in matchups if f'r{round_num}-{m["match_index"]}' not in results]
    skipped_count = len(matchups) - len(to_fetch)

    print(f"\nR{round_num}: {len(to_fetch)} to fetch, {skipped_count} already done")

    if to_fetch:
        # Estimate: ~1.1 fetches per matchup avg (10% need fallback)
        est_req = len(to_fetch) * 1.1
        # Rate: MAX_REQUESTS_PER_10MIN/WINDOW_SECONDS per second, parallelised by workers
        # But we're IO-bound so actual speed ≈ workers × (1 req per ~0.2s network latency)
        # Conservative: assume 1 req/s effective throughput regardless of workers
        est_secs = est_req / (MAX_REQUESTS_PER_10MIN / WINDOW_SECONDS)
        print(f"Workers: {num_workers}  |  Est. time: ~{int(est_secs)}s")
    print(f"{'─'*50}")

    start = time.time()
    confirmed = flagged = done = 0
    results_snapshot = dict(results)

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {
            executor.submit(process_matchup, round_num, m, results_snapshot): m
            for m in to_fetch
        }

        for future in as_completed(futures):
            key, result, status = future.result()
            done += 1

            if status == 'skipped':
                pass
            elif result:
                results[key] = result
                confirmed += 1
                tprint(f"  [{done}/{len(to_fetch)}] {status}")
            else:
                m = futures[future]
                pending[key] = {
                    'p1': m['p1'], 'p2': m['p2'],
                    'round': round_num,
                    'match_index': m['match_index'],
                    'note': 'Add "winner": "username" then run resolve_pending.py',
                    'flagged_at': datetime.now(timezone.utc).isoformat(),
                }
                flagged += 1
                tprint(f"  [{done}/{len(to_fetch)}] {m['p1']} vs {m['p2']}  {status}")

            if done % 50 == 0:
                save_json(RESULTS_FILE, results)
                save_json(PENDING_FILE, pending)
                tprint(f"  [checkpoint {done}/{len(to_fetch)}, {int(time.time()-start)}s elapsed]")

    elapsed = int(time.time() - start)
    print(f"\nDone in {elapsed}s: {confirmed} confirmed, {flagged} flagged, {skipped_count} skipped")
    return confirmed, flagged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--round',   type=int, required=True)
    parser.add_argument('--workers', type=int, default=5, help='Concurrent workers (default 5)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    r1_matchups = load_json(R1_FILE, [])
    results     = load_json(RESULTS_FILE, {})
    pending     = load_json(PENDING_FILE, {})

    if not r1_matchups:
        print("ERROR: scripts/r1_matchups.json not found.")
        return

    matchups = build_round_matchups(args.round, r1_matchups, results)

    if not matchups:
        print(f"No matchups found for R{args.round}.")
        if args.round > 1:
            n = sum(1 for k in results if k.startswith(f'r{args.round-1}-'))
            print(f"  ({n} results in R{args.round-1} — have all pending been resolved?)")
        return

    if args.dry_run:
        print(f"R{args.round}: {len(matchups)} matchups")
        for m in matchups[:10]:
            print(f"  r{args.round}-{m['match_index']}: {m['p1']} vs {m['p2']}")
        if len(matchups) > 10:
            print(f"  ... and {len(matchups)-10} more")
        return

    confirmed, flagged = process_round(args.round, matchups, results, pending, args.workers)

    results['_updated'] = datetime.now(timezone.utc).isoformat()
    save_json(RESULTS_FILE, results)
    save_json(PENDING_FILE, pending)
    print(f"\nSaved results.json ({sum(1 for k in results if not k.startswith('_'))} results)")

    if flagged:
        print(f"\n⚠  {flagged} flagged — edit scripts/pending_review.json then run:")
        print("   python3 scripts/resolve_pending.py")


if __name__ == '__main__':
    main()
