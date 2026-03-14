#!/usr/bin/env python3
import json, os

path = os.path.join(os.path.dirname(__file__), 'pending_review.json')
if not os.path.exists(path):
    print("No pending_review.json found.")
else:
    d = json.load(open(path))
    unresolved = {k: v for k, v in d.items() if not v.get('winner')}
    print(f"Matches needing manual review: {len(unresolved)}")
    for k, v in unresolved.items():
        print(f"  {k}: {v['p1']} vs {v['p2']}")
