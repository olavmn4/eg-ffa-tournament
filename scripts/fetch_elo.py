import json
import time
import urllib.request
import urllib.error
import os
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
USERNAMES_FILE = os.path.join(SCRIPT_DIR, 'usernames.json')
ELO_CACHE_FILE = os.path.join(SCRIPT_DIR, '..', 'elo_cache.json')
API_BASE = 'https://api.mcsrranked.com/users/'

DELAY_SECONDS = 1.5

def fetch_player(username):
    url = API_BASE + username
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'EG-FFA-Tournament/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            d = data.get('data') or {}

            season  = (d.get('statistics') or {}).get('season') or {}
            total   = (d.get('statistics') or {}).get('total')  or {}
            sr      = d.get('seasonResult') or {}

            return {
                'error': False,
                'nickname':      d.get('nickname'),
                'uuid':          d.get('uuid'),
                'country':       d.get('country'),
                'eloRate':       d.get('eloRate'),
                'eloRank':       d.get('eloRank'),
                'seasonHighest': sr.get('highest'),
                'seasonLowest':  sr.get('lowest'),
                'phasePoint':    (sr.get('last') or {}).get('phasePoint'),
                'season': {
                    'wins':          (season.get('wins')               or {}).get('ranked'),
                    'loses':         (season.get('loses')              or {}).get('ranked'),
                    'played':        (season.get('playedMatches')      or {}).get('ranked'),
                    'forfeits':      (season.get('forfeits')           or {}).get('ranked'),
                    'completions':   (season.get('completions')        or {}).get('ranked'),
                    'bestTime':      (season.get('bestTime')           or {}).get('ranked'),
                    'highestStreak': (season.get('highestWinStreak')   or {}).get('ranked'),
                    'currentStreak': (season.get('currentWinStreak')   or {}).get('ranked'),
                },
                'total': {
                    'wins':          (total.get('wins')                or {}).get('ranked'),
                    'loses':         (total.get('loses')               or {}).get('ranked'),
                    'played':        (total.get('playedMatches')       or {}).get('ranked'),
                    'bestTime':      (total.get('bestTime')            or {}).get('ranked'),
                    'highestStreak': (total.get('highestWinStreak')    or {}).get('ranked'),
                },
                'lastOnline': (d.get('timestamp') or {}).get('lastOnline'),
                'lastRanked': (d.get('timestamp') or {}).get('lastRanked'),
            }

    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"  [RATE LIMITED] Waiting 30s before retrying {username}...")
            time.sleep(30)
            return fetch_player(username)
        print(f"  [HTTP {e.code}] {username}")
        return {'error': True}
    except Exception as e:
        print(f"  [ERROR] {username}: {e}")
        return {'error': True}

def main():
    with open(USERNAMES_FILE) as f:
        usernames = json.load(f)

    total = len(usernames)
    print(f"Fetching data for {total} players at {DELAY_SECONDS}s intervals...")
    print(f"Estimated time: ~{total * DELAY_SECONDS / 60:.1f} minutes")

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

        if (i + 1) % 50 == 0 or (i + 1) == total:
            loaded = sum(1 for v in results.values() if not v['error'])
            print(f"  Progress: {i+1}/{total} | Loaded: {loaded} | Errors: {errors}")

        if (i + 1) % 100 == 0:
            save_cache(results)

        if i < total - 1:
            time.sleep(DELAY_SECONDS)

    save_cache(results)
    loaded = sum(1 for v in results.values() if not v['error'])
    print(f"\nDone! {loaded}/{total} players loaded, {errors} errors")

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
