#!/usr/bin/env python3
"""
Moves manually resolved entries from pending_review.json into results.json.

After flagging matches that couldn't be auto-resolved, you edit pending_review.json
to add a "winner" field to each entry, then run this script.

Example pending_review.json entry after manual edit:
  "r1-42": {
    "p1": "Kaltsi",
    "p2": "FazeBlaze",
    "round": 1,
    "match_index": 42,
    "winner": "Kaltsi",        <-- add this manually
    "note": "DQ - FazeBlaze no-show"
  }
"""

import json
import os
from datetime import datetime, timezone

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE  = os.path.join(SCRIPT_DIR, '..', 'results.json')
PENDING_FILE  = os.path.join(SCRIPT_DIR, 'pending_review.json')


def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception:
            pass
    return default


def main():
    results = load_json(RESULTS_FILE, {})
    pending = load_json(PENDING_FILE, {})

    resolved = []
    still_pending = {}

    for key, entry in pending.items():
        winner = entry.get('winner', '').strip()
        p1 = entry.get('p1', '')
        p2 = entry.get('p2', '')

        if not winner:
            still_pending[key] = entry
            continue

        # Validate winner is one of the two players
        if winner.lower() not in (p1.lower(), p2.lower()):
            print(f"  WARN: winner '{winner}' is not p1 '{p1}' or p2 '{p2}' for {key} — skipping")
            still_pending[key] = entry
            continue

        # Normalise to original casing
        winner_norm = p1 if winner.lower() == p1.lower() else p2
        loser_norm  = p2 if winner_norm == p1 else p1

        results[key] = {
            'winner': winner_norm,
            'loser':  loser_norm,
            'time_ms': entry.get('time_ms', None),
            'match_id': None,
            'date': None,
            'forfeited': entry.get('forfeited', False),
            'manual': True,
            'note': entry.get('note', ''),
        }
        resolved.append(f"  {key}: {winner_norm} beats {loser_norm}")

    if resolved:
        results['_updated'] = datetime.now(timezone.utc).isoformat()
        with open(RESULTS_FILE, 'w') as f:
            json.dump(results, f, indent=2)
        with open(PENDING_FILE, 'w') as f:
            json.dump(still_pending, f, indent=2)

        print(f"Resolved {len(resolved)} matches:")
        for line in resolved:
            print(line)
        if still_pending:
            print(f"\n{len(still_pending)} still pending (no winner set yet)")
    else:
        print("Nothing to resolve — add 'winner' fields to pending_review.json first")


if __name__ == '__main__':
    main()
