#!/usr/bin/env python3
"""
Fetches ELO data for all tournament players from api.mcsrranked.com
Rate limit: 500 requests per 10 minutes = 50 req/min safely
We use 40 req/min (1 request every 1.5s) to stay well under the limit.
Saves results to elo_cache.json which is read by the website.
"""

import json
import time
import urllib.request
import urllib.error
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
USERNAMES_FILE = os.path.join(SCRIPT_DIR, 'usernames.json')
ELO_CACHE_FILE = os.path.join(SCRIPT_DIR, '..', 'elo_cache.json')
API_BASE = 'https://api.mcsrranked.com/users/'

# 1.5s between requests = 40 req/min = 400 req/10min (well under 500 limit)
DELAY_SECONDS = 1.5

def fetch_player(username):
    url = API_BASE + username
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'EG-FFA-Tournament/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            player_data = data.get('data', {}) or {}
            elo = player_data.get('eloRate') or player_data.get('elo')
            rank = player_data.get('eloRank')
            return {'elo': elo, 'rank': rank, 'error': False}
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"  [RATE LIMITED] Waiting 30s before retrying {username}...")
            time.sleep(30)
            return fetch_player(username)  # retry once
        print(f"  [HTTP {e.code}] {username}")
        return {'elo': None, 'rank': None, 'error': True}
    except Exception as e:
        print(f"  [ERROR] {username}: {e}")
        return {'elo': None, 'rank': None, 'error': True}

def main():
    with open(USERNAMES_FILE) as f:
        usernames = json.load(f)

    total = len(usernames)
    print(f"Fetching ELO for {total} players at {DELAY_SECONDS}s intervals...")
    print(f"Estimated time: ~{total * DELAY_SECONDS / 60:.1f} minutes")

    # Load existing cache so we don't lose data on partial runs
    existing = {}
    if os.path.exists(ELO_CACHE_FILE):
        try:
            with open(ELO_CACHE_FILE) as f:
                cached = json.load(f)
                existing = cached.get('players', {})
            print(f"Loaded {len(existing)} existing entries from cache")
        except Exception:
            pass

    results = dict(existing)
    errors = 0

    for i, username in enumerate(usernames):
        result = fetch_player(username)
        results[username] = result
        if result['error']:
            errors += 1

        # Progress every 50 players
        if (i + 1) % 50 == 0 or (i + 1) == total:
            loaded = sum(1 for v in results.values() if not v['error'])
            print(f"  Progress: {i+1}/{total} | Loaded: {loaded} | Errors: {errors}")

        # Save incrementally every 100 players so partial runs aren't wasted
        if (i + 1) % 100 == 0:
            save_cache(results)

        if i < total - 1:
            time.sleep(DELAY_SECONDS)

    save_cache(results)
    loaded = sum(1 for v in results.values() if not v['error'])
    print(f"\nDone! {loaded}/{total} players loaded, {errors} errors")
    print(f"Cache saved to: {os.path.abspath(ELO_CACHE_FILE)}")

def save_cache(results):
    out = {
        'updated': datetime.now(timezone.utc).isoformat(),
        'players': results
    }
    os.makedirs(os.path.dirname(os.path.abspath(ELO_CACHE_FILE)), exist_ok=True)
    with open(ELO_CACHE_FILE, 'w') as f:
        json.dump(out, f)

if __name__ == '__main__':
    main()
