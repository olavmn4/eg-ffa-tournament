#!/usr/bin/env python3
"""
Fetches player data for all tournament players from api.mcsrranked.com
Rate limit: 500 requests per 10 minutes.
We use 1 request every 1.5s (~40/min) to stay well under the limit.
Saves results to players.json which is read by the website.
"""

import json
import time
import urllib.request
import urllib.error
import os
from datetime import datetime, timezone

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
USERNAMES_FILE = os.path.join(SCRIPT_DIR, 'usernames.json')
OUTPUT_FILE    = os.path.join(SCRIPT_DIR, '..', 'players.json')
API_BASE       = 'https://api.mcsrranked.com/users/'
DELAY_SECONDS  = 1.5

def fetch_player(username):
    try:
        req = urllib.request.Request(
            API_BASE + username,
            headers={'User-Agent': 'EG-FFA-Tournament/1.0'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode())

        d      = raw.get('data') or {}
        season = ((d.get('statistics') or {}).get('season') or {})
        total  = ((d.get('statistics') or {}).get('total')  or {})
        sr     = d.get('seasonResult') or {}

        def ranked(block, key):
            return (block.get(key) or {}).get('ranked')

        return {
            'error':   False,
            # identity
            'nickname': d.get('nickname'),
            'uuid':     d.get('uuid'),
            'country':  d.get('country'),
            'roleType': d.get('roleType'),
            # current elo
            'eloRate':  d.get('eloRate'),
            'eloRank':  d.get('eloRank'),
            # season peak/floor
            'seasonHighest': sr.get('highest'),
            'seasonLowest':  sr.get('lowest'),
            'phasePoint':    (sr.get('last') or {}).get('phasePoint'),
            # season stats
            'season': {
                'wins':          ranked(season, 'wins'),
                'loses':         ranked(season, 'loses'),
                'played':        ranked(season, 'playedMatches'),
                'forfeits':      ranked(season, 'forfeits'),
                'completions':   ranked(season, 'completions'),
                'bestTime':      ranked(season, 'bestTime'),
                'playtime':      ranked(season, 'playtime'),
                'completionTime':ranked(season, 'completionTime'),
                'highestStreak': ranked(season, 'highestWinStreak'),
                'currentStreak': ranked(season, 'currentWinStreak'),
            },
            # all-time stats
            'total': {
                'wins':          ranked(total, 'wins'),
                'loses':         ranked(total, 'loses'),
                'played':        ranked(total, 'playedMatches'),
                'forfeits':      ranked(total, 'forfeits'),
                'completions':   ranked(total, 'completions'),
                'bestTime':      ranked(total, 'bestTime'),
                'playtime':      ranked(total, 'playtime'),
                'completionTime':ranked(total, 'completionTime'),
                'highestStreak': ranked(total, 'highestWinStreak'),
                'currentStreak': ranked(total, 'currentWinStreak'),
            },
            # timestamps
            'firstOnline': (d.get('timestamp') or {}).get('firstOnline'),
            'lastOnline':  (d.get('timestamp') or {}).get('lastOnline'),
            'lastRanked':  (d.get('timestamp') or {}).get('lastRanked'),
            'nextDecay':   (d.get('timestamp') or {}).get('nextDecay'),
        }

    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"  [RATE LIMITED] waiting 30s then retrying {username}...")
            time.sleep(30)
            return fetch_player(username)
        print(f"  [HTTP {e.code}] {username}")
        return {'error': True}
    except Exception as e:
        print(f"  [ERROR] {username}: {e}")
        return {'error': True}


def save(results):
    with open(OUTPUT_FILE, 'w') as f:
        json.dump({
            'updated': datetime.now(timezone.utc).isoformat(),
            'players': results
        }, f)


def main():
    with open(USERNAMES_FILE) as f:
        usernames = json.load(f)

    total = len(usernames)
    print(f"Fetching {total} players at {DELAY_SECONDS}s/req (~{total*DELAY_SECONDS/60:.0f} min)...")

    # Load existing so partial runs don't lose data
    results = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            results = json.load(open(OUTPUT_FILE)).get('players', {})
            print(f"  Resuming — {len(results)} already cached")
        except Exception:
            pass

    errors = 0
    for i, username in enumerate(usernames):
        results[username] = fetch_player(username)
        if results[username]['error']:
            errors += 1

        if (i + 1) % 50 == 0 or (i + 1) == total:
            loaded = sum(1 for v in results.values() if not v.get('error'))
            print(f"  {i+1}/{total} — {loaded} loaded, {errors} errors")

        if (i + 1) % 100 == 0:
            save(results)

        if i < total - 1:
            time.sleep(DELAY_SECONDS)

    save(results)
    print(f"Done. players.json written.")


if __name__ == '__main__':
    main()
