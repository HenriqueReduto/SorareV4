from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SORARE_PATH = ROOT / "data" / "sorare" / "sorare_scores.csv"
MAIN_PATH = ROOT / "data" / "main" / "main.csv"
SOFASCORE_PATH = ROOT / "data" / "sofascore" / "sofascore_player_match_stats.csv"
OUTPUT_PATH = ROOT / "data" / "player_ids" / "sorare_transfermarkt_sofascore_player_matches_review.xlsx"


CLUB_TO_TRACKED_CLUB = {
    "benfica-lisboa": "Benfica",
    "besiktas-istanbul": "Besiktas",
    "celtic-glasgow": "Celtic FC",
    "fenerbahce-istanbul": "Fenerbahce",
    "galatasaray-istanbul": "Galatasaray",
    "porto-porto": "Porto",
    "rangers-glasgow": "Rangers FC",
    "salzburg-wals-siezenheim": "Red Bull Salzburg",
    "sporting-braga-braga": "Sporting Braga",
    "sporting-cp-lisboa": "Sporting CP",
    "trabzonspor-trabzon": "Trabzonspor",
    "vitoria-guimaraes-guimaraes": "Vitoria Guimaraes",
}


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.casefold())).strip()


def ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    token_score = 0.0
    if left_tokens and right_tokens:
        token_score = len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))
    return max(SequenceMatcher(None, left, right).ratio(), token_score)


def first_nonblank(series: pd.Series) -> str:
    values = series.dropna().astype(str)
    values = values[values.str.strip().ne("")]
    if values.empty:
        return ""
    modes = values.mode()
    return modes.iloc[0] if not modes.empty else values.iloc[0]


def clean_identifier(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def build_sorare_base() -> pd.DataFrame:
    sorare = pd.read_csv(SORARE_PATH, low_memory=False)
    base = (
        sorare[["Club", "Club Slug", "Player", "Player Slug", "Position"]]
        .drop_duplicates()
        .sort_values(["Club Slug", "Player"])
        .reset_index(drop=True)
    )
    base["tracked_club"] = base["Club Slug"].map(CLUB_TO_TRACKED_CLUB).fillna("")
    return base


def build_transfermarkt_map() -> pd.DataFrame:
    main = pd.read_csv(
        MAIN_PATH,
        low_memory=False,
        usecols=[
            "Club Slug",
            "Player Slug",
            "transfermarkt_TransfermarktPlayerId",
            "transfermarkt_TransfermarktPlayerName",
        ],
    )
    grouped = (
        main.groupby(["Club Slug", "Player Slug"], dropna=False)
        .agg(
            tm_player_id=("transfermarkt_TransfermarktPlayerId", first_nonblank),
            tm_player_name=("transfermarkt_TransfermarktPlayerName", first_nonblank),
        )
        .reset_index()
    )
    grouped["tm_player_id"] = grouped["tm_player_id"].map(clean_identifier)
    return grouped


def build_sofascore_players() -> pd.DataFrame:
    sofa = pd.read_csv(
        SOFASCORE_PATH,
        low_memory=False,
        usecols=[
            "tracked_club",
            "tracked_team_id",
            "player_team",
            "player_team_id",
            "player_id",
            "player_name",
            "player_slug",
            "player_position",
            "match_date",
            "event_id",
            "minutes_played",
        ],
    )
    sofa["match_date"] = pd.to_datetime(sofa["match_date"], errors="coerce")
    sofa["minutes_played"] = pd.to_numeric(sofa["minutes_played"], errors="coerce")
    grouped = (
        sofa.groupby(["tracked_club", "player_id"], dropna=False)
        .agg(
            sofascore_player_name=("player_name", first_nonblank),
            sofascore_player_slug=("player_slug", first_nonblank),
            sofascore_player_position=("player_position", first_nonblank),
            sofascore_tracked_team_id=("tracked_team_id", first_nonblank),
            sofascore_player_team=("player_team", first_nonblank),
            sofascore_player_team_id=("player_team_id", first_nonblank),
            sofascore_rows=("event_id", "size"),
            sofascore_first_match=("match_date", "min"),
            sofascore_last_match=("match_date", "max"),
            sofascore_minutes=("minutes_played", "sum"),
        )
        .reset_index()
        .rename(columns={"player_id": "sofascore_player_id"})
    )
    for column in ["sofascore_player_id", "sofascore_tracked_team_id", "sofascore_player_team_id"]:
        grouped[column] = grouped[column].map(clean_identifier)
    grouped["sofascore_player_norm"] = grouped["sofascore_player_name"].map(normalize)
    return grouped


def best_sofascore_match(row: pd.Series, sofa_by_club: dict[str, pd.DataFrame]) -> dict[str, object]:
    candidates = sofa_by_club.get(row["tracked_club"], pd.DataFrame())
    if candidates.empty:
        return {
            "match_status": "no_sofascore_club_rows",
            "match_score": "",
            "match_source": "",
        }

    sorare_norm = normalize(row["Player"])
    tm_norm = normalize(row.get("tm_player_name", ""))
    player_slug = str(row.get("Player Slug", "") or "")

    best = None
    for _, candidate in candidates.iterrows():
        sofa_norm = candidate["sofascore_player_norm"]
        sorare_score = ratio(sorare_norm, sofa_norm)
        tm_score = ratio(tm_norm, sofa_norm)
        slug_match = player_slug and player_slug == str(candidate["sofascore_player_slug"])
        score = max(sorare_score, tm_score, 1.0 if slug_match else 0.0)
        if best is None or score > best["match_score"]:
            candidate_data = candidate.drop(labels=["tracked_club", "sofascore_player_norm"], errors="ignore").to_dict()
            best = {
                **candidate_data,
                "match_score": round(float(score), 4),
                "sorare_name_score": round(float(sorare_score), 4),
                "transfermarkt_name_score": round(float(tm_score), 4),
                "match_source": "player_slug" if slug_match else ("transfermarkt_player_name" if tm_score >= sorare_score else "sorare_player_name"),
            }

    if best is None or best["match_score"] < 0.82:
        return {
            "match_status": "unmatched",
            "match_score": best["match_score"] if best else "",
            "match_source": best["match_source"] if best else "",
            "closest_sofascore_player_name": best.get("sofascore_player_name", "") if best else "",
            "closest_sofascore_player_id": best.get("sofascore_player_id", "") if best else "",
        }

    if best["match_score"] == 1.0:
        best["match_status"] = "exact"
    elif best["match_score"] >= 0.92:
        best["match_status"] = "strong_fuzzy"
    else:
        best["match_status"] = "review_fuzzy"
    return best


def build_review() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sorare = build_sorare_base()
    tm_map = build_transfermarkt_map()
    sofa = build_sofascore_players()

    review = sorare.merge(tm_map, on=["Club Slug", "Player Slug"], how="left")
    review[["tm_player_id", "tm_player_name"]] = review[["tm_player_id", "tm_player_name"]].fillna("")
    sofa_by_club = {club: rows.reset_index(drop=True) for club, rows in sofa.groupby("tracked_club", dropna=False)}

    match_rows = []
    for _, row in review.iterrows():
        match = best_sofascore_match(row, sofa_by_club)
        match_rows.append(match)

    matches = pd.DataFrame(match_rows)
    review = pd.concat([review.reset_index(drop=True), matches.reset_index(drop=True)], axis=1)

    output_columns = [
        "Club",
        "Club Slug",
        "tracked_club",
        "Player",
        "Player Slug",
        "Position",
        "tm_player_name",
        "tm_player_id",
        "match_status",
        "match_score",
        "match_source",
        "sorare_name_score",
        "transfermarkt_name_score",
        "sofascore_player_name",
        "sofascore_player_id",
        "sofascore_player_slug",
        "sofascore_player_position",
        "sofascore_player_team",
        "sofascore_player_team_id",
        "sofascore_rows",
        "sofascore_first_match",
        "sofascore_last_match",
        "sofascore_minutes",
        "closest_sofascore_player_name",
        "closest_sofascore_player_id",
        "manual_sofascore_player_name",
        "manual_sofascore_player_id",
        "review_notes",
    ]
    for column in output_columns:
        if column not in review.columns:
            review[column] = ""
    review = review[output_columns]

    unmatched = review[~review["match_status"].isin(["exact", "strong_fuzzy", "review_fuzzy"])].copy()

    matched_review = review.copy()
    matched_review["sofascore_player_id"] = matched_review["sofascore_player_id"].map(clean_identifier)
    matched_review = matched_review[matched_review["sofascore_player_id"].ne("")]
    matched_sofa_keys = set(zip(matched_review["tracked_club"], matched_review["sofascore_player_id"]))
    sofa["matched_to_sorare_or_transfermarkt"] = [
        (row.tracked_club, clean_identifier(row.sofascore_player_id)) in matched_sofa_keys
        for row in sofa.itertuples(index=False)
    ]
    unmatched_sofa = sofa[~sofa["matched_to_sorare_or_transfermarkt"]].copy()
    unmatched_sofa = unmatched_sofa[
        [
            "tracked_club",
            "sofascore_tracked_team_id",
            "sofascore_player_team",
            "sofascore_player_team_id",
            "sofascore_player_name",
            "sofascore_player_id",
            "sofascore_player_slug",
            "sofascore_player_position",
            "sofascore_rows",
            "sofascore_first_match",
            "sofascore_last_match",
            "sofascore_minutes",
        ]
    ].sort_values(["tracked_club", "sofascore_player_name"])

    summary = pd.DataFrame(
        [
            {"Metric": "Total Sorare player rows", "Count": len(review)},
            {"Metric": "Matched rows", "Count": int(review["match_status"].isin(["exact", "strong_fuzzy", "review_fuzzy"]).sum())},
            {"Metric": "Exact rows", "Count": int(review["match_status"].eq("exact").sum())},
            {"Metric": "Strong fuzzy rows", "Count": int(review["match_status"].eq("strong_fuzzy").sum())},
            {"Metric": "Review fuzzy rows", "Count": int(review["match_status"].eq("review_fuzzy").sum())},
            {"Metric": "Unmatched Sorare rows", "Count": len(unmatched)},
            {"Metric": "Unique SofaScore player rows", "Count": len(sofa)},
            {"Metric": "Unmatched SofaScore rows", "Count": len(unmatched_sofa)},
        ]
    )

    return review, unmatched, summary, unmatched_sofa


def write_workbook() -> None:
    review, unmatched, summary, unmatched_sofa = build_review()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl", datetime_format="yyyy-mm-dd") as writer:
        review.to_excel(writer, sheet_name="All Matches", index=False)
        unmatched.to_excel(writer, sheet_name="Unmatched", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)
        unmatched_sofa.to_excel(writer, sheet_name="Unmatched Sofascore", index=False)

        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for column_cells in worksheet.columns:
                header = str(column_cells[0].value or "")
                width = min(max(len(header) + 2, 12), 42)
                worksheet.column_dimensions[column_cells[0].column_letter].width = width

    print(f"Wrote {OUTPUT_PATH}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    write_workbook()
