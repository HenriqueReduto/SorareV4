# Sorare V4 Dashboard

Gradio dashboard modeled after the SORARE V3 dashboard, adapted to the current SORARE V4 datasets:

- `data/main/main.csv`
- `data/scores_breakdown/scores_breakdown.csv`
- `data/main/teams.csv`
- `data/sofascore/data_raw_main_sofascore_match_stats.csv`

The Players tab uses Transfermarkt matchday minutes, goals, and assists when present in `main.csv`. The Transfermarkt tab summarizes club-date coverage and highlights any fixture dates where no matchday squad is available.

## Run Locally

From the `SORARE V4` folder:

```powershell
pip install -r dashboard/requirements.txt
python dashboard/launch_local.py
```

The app will use the first free port from `7861` to `7870`.
