# EG FFA — MCSR 1000-Player Tournament Site

A static tournament bracket site with automatic hourly ELO updates via GitHub Actions.

## Setup (takes ~5 minutes)

### 1. Create a GitHub repository
- Go to [github.com](https://github.com) → **New repository**
- Name it anything, e.g. `eg-ffa-tournament`
- Set it to **Public** (required for free GitHub Pages)
- **Don't** initialize with a README

### 2. Upload these files
Upload all files in this folder to the root of your new repository.
You can drag-and-drop them in the GitHub web interface, or use git:

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/eg-ffa-tournament.git
git push -u origin main
```

### 3. Enable GitHub Pages
- Go to your repo → **Settings** → **Pages**
- Under "Source", select **Deploy from a branch**
- Branch: `main`, folder: `/ (root)`
- Click **Save**
- Your site will be live at `https://YOUR_USERNAME.github.io/eg-ffa-tournament/`

### 4. Run the first ELO fetch manually
- Go to your repo → **Actions** tab
- Click **"Update ELO Data"** in the left sidebar
- Click **"Run workflow"** → **"Run workflow"** (green button)
- This takes ~24 minutes to fetch all 956 players at the safe rate limit
- After it completes, the site will show live ELO data

### 5. Automatic updates
The workflow runs **automatically every hour** at :05 past the hour.
No further action needed — it will keep the ELO data fresh.

---

## How it works

- `index.html` — the tournament website (bracket + player list)
- `elo_cache.json` — ELO data fetched from `api.mcsrranked.com`, updated hourly
- `scripts/fetch_elo.py` — fetches ELO for all players at 1 request/1.5s (~40 req/min, well under the 500/10min API limit)
- `.github/workflows/update-elo.yml` — GitHub Action that runs `fetch_elo.py` every hour and commits the updated cache

## Files
```
├── index.html                          ← Main website
├── elo_cache.json                      ← Auto-updated ELO data
├── scripts/
│   ├── fetch_elo.py                    ← ELO fetcher script
│   ├── matches.json                    ← Bracket match data
│   └── usernames.json                  ← Player username list
└── .github/
    └── workflows/
        └── update-elo.yml              ← Hourly update action
```
