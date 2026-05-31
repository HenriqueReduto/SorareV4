from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
MAIN_PATH = ROOT / "data" / "main" / "main.csv"
BACKUP_PATH = ROOT / "data" / "main" / "main_before_review_sofascore_player_stats.csv"
REVIEW_PATH = ROOT / "data" / "player_ids" / "sorare_transfermarkt_sofascore_player_matches_review.xlsx"
SOFASCORE_PATH = ROOT / "data" / "sofascore" / "sofascore_player_match_stats.csv"


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


METADATA_RENAMES = {
    "tracked_club": "player_sofascore_tracked_club",
    "tracked_team_id": "player_sofascore_tracked_team_id",
    "event_id": "player_sofascore_event_id",
    "event_slug": "player_sofascore_event_slug",
    "match_date": "player_sofascore_match_date",
    "start_timestamp": "player_sofascore_start_timestamp",
    "status": "player_sofascore_status",
    "tournament": "player_sofascore_tournament",
    "season": "player_sofascore_season",
    "round": "player_sofascore_round",
    "home_team": "player_sofascore_home_team",
    "home_team_id": "player_sofascore_home_team_id",
    "home_score": "player_sofascore_home_score",
    "away_team": "player_sofascore_away_team",
    "away_team_id": "player_sofascore_away_team_id",
    "away_score": "player_sofascore_away_score",
    "player_team": "player_sofascore_player_team",
    "player_team_id": "player_sofascore_player_team_id",
    "is_home": "player_sofascore_is_home",
    "player_id": "player_sofascore_player_id",
    "player_name": "player_sofascore_player_name",
    "player_slug": "player_sofascore_player_slug",
    "player_position": "player_sofascore_player_position",
    "shirt_number": "player_sofascore_shirt_number",
    "starter": "player_sofascore_starter",
    "substitute": "player_sofascore_substitute",
    "captain": "player_sofascore_captain",
    "stats_available": "player_sofascore_stats_available",
    "minutes_played": "player_sofascore_minutes_played",
    "rating": "player_sofascore_rating",
}


REVIEW_COLUMNS = [
    "player_sofascore_review_player_id",
    "player_sofascore_review_player_name",
    "player_sofascore_review_status",
    "player_sofascore_review_score",
    "player_sofascore_review_source",
]


def clean_identifier(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.casefold())).strip()


def first_nonblank(values: pd.Series) -> str:
    values = values.dropna().astype(str).str.strip()
    values = values[values.ne("")]
    return values.iloc[0] if not values.empty else ""


def effective_review_value(row: pd.Series, manual_column: str, auto_column: str) -> str:
    manual = clean_identifier(row.get(manual_column, ""))
    return manual if manual else clean_identifier(row.get(auto_column, ""))


def load_review(sofa_players: pd.DataFrame) -> pd.DataFrame:
    review = pd.read_excel(REVIEW_PATH, sheet_name="All Matches", dtype=str).fillna("")

    sofa_name_lookup = (
        sofa_players.assign(
            tracked_club_norm=sofa_players["tracked_club"].astype(str),
            player_norm=sofa_players["player_name"].map(normalize_text),
            player_id_clean=sofa_players["player_id"].map(clean_identifier),
        )
        .groupby(["tracked_club_norm", "player_norm"])["player_id_clean"]
        .agg(lambda ids: ids.iloc[0] if ids.nunique() == 1 else "")
        .to_dict()
    )

    review["player_sofascore_review_player_id"] = review.apply(
        lambda row: effective_review_value(row, "manual_sofascore_player_id", "sofascore_player_id"),
        axis=1,
    )
    review["player_sofascore_review_player_name"] = review.apply(
        lambda row: first_nonblank(
            pd.Series([row.get("manual_sofascore_player_name", ""), row.get("sofascore_player_name", "")])
        ),
        axis=1,
    )

    missing_id = review["player_sofascore_review_player_id"].eq("") & review["player_sofascore_review_player_name"].ne("")
    if missing_id.any():
        review.loc[missing_id, "player_sofascore_review_player_id"] = review.loc[missing_id].apply(
            lambda row: sofa_name_lookup.get((row.get("tracked_club", ""), normalize_text(row["player_sofascore_review_player_name"])), ""),
            axis=1,
        )

    review["player_sofascore_review_status"] = review.get("match_status", "")
    review["player_sofascore_review_score"] = review.get("match_score", "")
    review["player_sofascore_review_source"] = review.get("match_source", "")

    return review[
        [
            "Club Slug",
            "Player Slug",
            *REVIEW_COLUMNS,
        ]
    ].drop_duplicates(["Club Slug", "Player Slug"], keep="first")


def prepare_sofascore() -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    sofa = pd.read_csv(SOFASCORE_PATH, low_memory=False, dtype=str).fillna("")
    for column in ["event_id", "player_id", "tracked_team_id", "home_team_id", "away_team_id", "player_team_id"]:
        if column in sofa.columns:
            sofa[column] = sofa[column].map(clean_identifier)

    sofa["match_date_key"] = pd.to_datetime(sofa["match_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    sofa["event_player_key"] = sofa["event_id"] + "||" + sofa["player_id"]
    sofa["club_date_player_key"] = sofa["tracked_club"] + "||" + sofa["match_date_key"] + "||" + sofa["player_id"]

    sofa = sofa.drop_duplicates("event_player_key", keep="first")

    mapped_columns: list[tuple[str, str]] = []
    for source_column in sofa.columns:
        if source_column in {"event_player_key", "club_date_player_key", "match_date_key"}:
            continue
        target_column = METADATA_RENAMES.get(source_column, f"player_{source_column}")
        mapped_columns.append((source_column, target_column))

    return sofa, mapped_columns


def empty_series(index: pd.Index) -> pd.Series:
    return pd.Series([""] * len(index), index=index, dtype="object")


def apply_sofascore_stats() -> None:
    for path in [MAIN_PATH, REVIEW_PATH, SOFASCORE_PATH]:
        if not path.exists():
            raise FileNotFoundError(path)

    if not BACKUP_PATH.exists():
        shutil.copy2(MAIN_PATH, BACKUP_PATH)

    main = pd.read_csv(MAIN_PATH, low_memory=False, dtype=str).fillna("")
    sofa, mapped_columns = prepare_sofascore()
    review = load_review(sofa)

    repeat_columns = REVIEW_COLUMNS + [
        "player_sofascore_review_matched",
        "player_sofascore_tracked_club_expected",
        "player_sofascore_game_date_key",
    ]
    main = main.drop(columns=[column for column in repeat_columns if column in main.columns])
    main = main.merge(review, on=["Club Slug", "Player Slug"], how="left")
    for column in REVIEW_COLUMNS:
        if column not in main.columns:
            main[column] = ""
        main[column] = main[column].fillna("").map(clean_identifier if column.endswith("_id") else str)

    main["player_sofascore_review_matched"] = main["player_sofascore_review_player_id"].ne("")
    main["player_sofascore_tracked_club_expected"] = main["Club Slug"].map(CLUB_TO_TRACKED_CLUB).fillna("")
    main["player_sofascore_game_date_key"] = pd.to_datetime(main["Game Date"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d").fillna("")
    main["player_sofascore_event_player_key"] = (
        main.get("sofascore_event_id", "").map(clean_identifier)
        + "||"
        + main["player_sofascore_review_player_id"]
    )
    main["player_sofascore_club_date_player_key"] = (
        main["player_sofascore_tracked_club_expected"]
        + "||"
        + main["player_sofascore_game_date_key"]
        + "||"
        + main["player_sofascore_review_player_id"]
    )

    primary = main[["player_sofascore_event_player_key"]].merge(
        sofa,
        left_on="player_sofascore_event_player_key",
        right_on="event_player_key",
        how="left",
    )
    fallback = main[["player_sofascore_club_date_player_key"]].merge(
        sofa.drop_duplicates("club_date_player_key", keep="first"),
        left_on="player_sofascore_club_date_player_key",
        right_on="club_date_player_key",
        how="left",
    )

    primary_found = primary["event_id"].fillna("").astype(str).str.strip().ne("")
    fallback_found = fallback["event_id"].fillna("").astype(str).str.strip().ne("")

    main["player_sofascore_match_found"] = primary_found | (~primary_found & fallback_found)
    main["player_sofascore_match_source"] = ""
    main.loc[primary_found, "player_sofascore_match_source"] = "event_id"
    main.loc[~primary_found & fallback_found, "player_sofascore_match_source"] = "club_date"

    for source_column, target_column in mapped_columns:
        values = primary[source_column].where(primary_found, fallback[source_column].where(fallback_found, ""))
        main[target_column] = values.fillna("").astype(str)

    main["player_sofascore_context_source"] = str(REVIEW_PATH)

    helper_columns = [
        "player_sofascore_event_player_key",
        "player_sofascore_club_date_player_key",
    ]
    main = main.drop(columns=[column for column in helper_columns if column in main.columns])

    main.to_csv(MAIN_PATH, index=False)

    total_rows = len(main)
    mapped_rows = int(main["player_sofascore_review_matched"].sum())
    matched_rows = int(main["player_sofascore_match_found"].sum())
    primary_rows = int((main["player_sofascore_match_source"] == "event_id").sum())
    fallback_rows = int((main["player_sofascore_match_source"] == "club_date").sum())
    print(f"Wrote {MAIN_PATH}")
    print(f"Rows: {total_rows}")
    print(f"Rows with reviewed SofaScore player ID: {mapped_rows}")
    print(f"Rows with SofaScore player match stats: {matched_rows}")
    print(f"Matched by event_id: {primary_rows}")
    print(f"Matched by club/date fallback: {fallback_rows}")
    print(f"Backup: {BACKUP_PATH}")


if __name__ == "__main__":
    apply_sofascore_stats()
