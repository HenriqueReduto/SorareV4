from pathlib import Path
import unicodedata

import gradio as gr
import pandas as pd
import plotly.express as px

try:
    from .sorare_scoring_matrix import DECISIVE_LEVEL_POINTS, SOFASCORE_RAW_STAT_COLUMNS, SORARE_SCORING_MATRIX
except ImportError:
    from sorare_scoring_matrix import DECISIVE_LEVEL_POINTS, SOFASCORE_RAW_STAT_COLUMNS, SORARE_SCORING_MATRIX


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = PROJECT_ROOT / "data" / "main" / "main.csv"
SCORE_BREAKDOWN_PATH = PROJECT_ROOT / "data" / "scores_breakdown" / "scores_breakdown.csv"
TEAM_PATH = PROJECT_ROOT / "data" / "main" / "teams.csv"
MATCH_STATS_PATH = PROJECT_ROOT / "data" / "sofascore" / "data_raw_main_sofascore_match_stats.csv"
SCORING_MATRIX_PATH = PROJECT_ROOT / "data" / "scores_breakdown" / "sorare_matrix" / "data" / "scoring_matrix_new.csv"


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def _to_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = df.copy()
    for column in columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _choices(df: pd.DataFrame, column: str, include_all: bool = True) -> list[str]:
    if df.empty or column not in df.columns:
        return ["All"] if include_all else []
    values = sorted(value for value in df[column].dropna().astype(str).unique().tolist() if value.strip())
    return (["All"] if include_all else []) + values


def _filter_text(df: pd.DataFrame, query: str, columns: list[str]) -> pd.DataFrame:
    if not query or df.empty:
        return df
    query = _normalize_text(query)
    mask = pd.Series(False, index=df.index)
    for column in columns:
        if column in df.columns:
            mask = mask | df[column].fillna("").astype(str).map(_normalize_text).str.contains(query, regex=False)
    return df[mask]


def _lineup_minutes(status: object) -> float:
    value = str(status).casefold()
    if value == "starter":
        return 90.0
    if value in {"bench", "dnp"}:
        return 0.0
    return float("nan")


SCORE_BAND_ORDER = [
    "DNP",
    "0 - 24.99",
    "25 - 34.99",
    "35 - 49.99",
    "50 - 59.99",
    "60 - 74.99",
    "75 - 99.99",
    "100",
]

SCORE_BAND_COLORS = {
    "DNP": "#3f3f46",
    "0 - 24.99": "#ef4444",
    "25 - 34.99": "#f97316",
    "35 - 49.99": "#facc15",
    "50 - 59.99": "#86efac",
    "60 - 74.99": "#15803d",
    "75 - 99.99": "#7dd3fc",
    "100": "#7b2cbf",
}


CATEGORY_TABLES = [
    ("Decisive Actions", "Score Decisive Actions", "Decisive"),
    ("Attacking", "Score Attacking", "Attacking"),
    ("Passing", "Score Passing", "Passing"),
    ("Defending", "Score Defending", "Defending"),
    ("Duels", "Score Duels", "Duels"),
    ("Possesion", "Score Possesion", "Possession"),
    ("Discipline", "Score Discipline", "Discipline"),
    ("Goalkeeping", "Score Goalkeeping", "Goalkeeping"),
]

MATRIX_STAT_BY_MAIN_COLUMN = {
    "v3_TMYellowCards": "YELLOW_CARD",
    "player_fouls": "FOULS",
    "player_was_fouled": "WAS_FOULED",
    "player_error_lead_to_a_shot": "ERROR_LEAD_TO_SHOT",
    "player_clean_sheet_60": "CLEAN_SHEET_60",
    "player_goals_conceded": "GOALS_CONCEDED",
    "player_total_clearance": "EFFECTIVE_CLEARANCE",
    "player_won_tackle": "WON_TACKLE",
    "player_outfielder_block": "OUTFIELDER_BLOCK",
    "player_possession_lost_ctrl": "POSS_LOST_CTRL",
    "player_ball_recovery": "POSS_WON",
    "player_duel_lost": "DUEL_LOST",
    "player_duel_won": "DUEL_WON",
    "player_interception_won": "INTERCEPTION_WON",
    "player_big_chance_created": "BIG_CHANCE_CREATED",
    "player_key_pass": "ADJUSTED_TOTAL_ATT_ASSIST",
    "player_accurate_pass": "ACCURATE_PASS",
    "player_accurate_long_balls": "ACCURATE_LONG_BALLS",
    "player_missed_pass": "MISSED_PASS",
    "player_on_target_scoring_attempt": "ONTARGET_SCORING_ATT",
    "player_won_contest": "WON_CONTEST",
    "player_penalty_miss": "PENALTY_KICK_MISSED",
    "player_big_chance_missed": "BIG_CHANCE_MISSED",
    "player_saves": "SAVES",
    "player_saved_shots_from_inside_the_box": "SAVED_IBOX",
    "player_good_high_claim": "GOOD_HIGH_CLAIM",
    "player_punches": "PUNCHES",
    "player_cross_not_claimed": "CROSS_NOT_CLAIMED",
    "player_accurate_keeper_sweeper": "ACCURATE_KEEPER_SWEEPER",
}


def _load_scoring_matrix(path: Path) -> dict[str, dict[str, float | None]]:
    if not path.exists():
        return {}
    matrix = pd.read_csv(path)
    weights: dict[str, dict[str, float | None]] = {}
    for _, row in matrix.iterrows():
        stat = str(row.get("Stat", "")).strip()
        if not stat:
            continue
        weights[stat] = {}
        for position in ["GK", "DEF", "MID", "FWD"]:
            value = pd.to_numeric(row.get(position), errors="coerce")
            weights[stat][position] = None if pd.isna(value) else float(value)
    return weights


def _score_band(row: pd.Series) -> str:
    if bool(row.get("is_dnp", False)):
        return "DNP"
    score = pd.to_numeric(row.get("Score"), errors="coerce")
    if pd.isna(score):
        return "DNP"
    if score >= 100:
        return "100"
    if score >= 75:
        return "75 - 99.99"
    if score >= 60:
        return "60 - 74.99"
    if score >= 50:
        return "50 - 59.99"
    if score >= 35:
        return "35 - 49.99"
    if score >= 25:
        return "25 - 34.99"
    return "0 - 24.99"


def _prepare_main(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    result["Game Date"] = pd.to_datetime(result.get("Game Date"), errors="coerce")
    if "transfermarkt_TransfermarktMatchDate" in result.columns:
        result["transfermarkt_TransfermarktMatchDate"] = pd.to_datetime(
            result["transfermarkt_TransfermarktMatchDate"],
            errors="coerce",
        )
    numeric_columns = [
        "Score",
        "sofascore_expected_goals_value",
        "sofascore_ball_possession_value",
        "sofascore_total_shots_value",
        "sofascore_shots_on_target_value",
        "sofascore_corner_kicks_value",
        "sofascore_fouls_value",
        "sofascore_yellow_cards_value",
        "sofascore_accurate_passes_value",
        "sofascore_goalkeeper_saves_value",
        "transfermarkt_RestDays",
        "transfermarkt_TransfermarktDateDeltaDays",
        "transfermarkt_TMMinutesPlayed",
        "transfermarkt_TMGoals",
        "transfermarkt_TMAssists",
        "v3_TeamGoalsAgainst",
        "player_sofascore_minutes_played",
        "player_sofascore_rating",
        "player_goals",
        "player_goal_assist",
        "player_expected_goals",
        "player_expected_assists",
        "player_total_shots",
        "player_on_target_scoring_attempt",
        "player_key_pass",
        "player_total_pass",
        "player_accurate_pass",
        "player_duel_won",
        "player_total_tackle",
        "player_interception_won",
        "player_total_clearance",
        "player_ball_recovery",
        "player_saves",
        "player_goals_prevented",
        "player_error_lead_to_a_shot",
        "v3_TMYellowCards",
        "v3_TMRedCards",
    ]
    numeric_columns.extend(
        config["main_column"]
        for config in SORARE_SCORING_MATRIX.values()
        if config.get("main_column") not in numeric_columns
    )
    numeric_columns.extend(
        f"player_{column}"
        for column in SOFASCORE_RAW_STAT_COLUMNS
        if f"player_{column}" in result.columns and f"player_{column}" not in numeric_columns
    )
    result = _to_numeric(result, numeric_columns).copy()
    result["estimated_minutes"] = result.get("transfermarkt_LineupStatus", "").map(_lineup_minutes)
    if "transfermarkt_TMMinutesPlayed" in result.columns:
        result["tm_minutes"] = result["transfermarkt_TMMinutesPlayed"].fillna(result["estimated_minutes"])
    else:
        result["tm_minutes"] = result["estimated_minutes"]
    result["is_starter"] = result.get("transfermarkt_LineupStatus", "").astype(str).str.casefold().eq("starter")
    result["is_bench"] = result.get("transfermarkt_LineupStatus", "").astype(str).str.casefold().eq("bench")
    result["is_dnp"] = result.get("transfermarkt_LineupStatus", "").astype(str).str.casefold().eq("dnp")
    result["tm_in_matchday_squad"] = result["is_starter"] | result["is_bench"]
    result["is_played"] = result["is_starter"] | (pd.to_numeric(result["Score"], errors="coerce").fillna(0) > 0)
    result["tm_goals"] = result.get("transfermarkt_TMGoals", pd.Series(0, index=result.index)).fillna(0)
    result["tm_assists"] = result.get("transfermarkt_TMAssists", pd.Series(0, index=result.index)).fillna(0)
    result["gk_clean_sheet"] = (
        result.get("Position", "").astype(str).str.casefold().str.contains("goalkeeper", na=False)
        & result["tm_minutes"].fillna(0).ge(60)
        & result.get("v3_TeamGoalsAgainst", pd.Series(0, index=result.index)).fillna(0).eq(0)
    ).astype(float)
    result["player_clean_sheet_60"] = (
        result["tm_minutes"].fillna(0).ge(60)
        & result.get("v3_TeamGoalsAgainst", pd.Series(0, index=result.index)).fillna(0).eq(0)
    ).astype(float)
    result["player_gk_clean_sheet"] = result["gk_clean_sheet"]
    result["player_goals_conceded"] = result.get("v3_TeamGoalsAgainst", pd.Series(0, index=result.index)).fillna(0)
    result["player_missed_pass"] = (
        result.get("player_total_pass", pd.Series(0, index=result.index)).fillna(0)
        - result.get("player_accurate_pass", pd.Series(0, index=result.index)).fillna(0)
    ).clip(lower=0)
    result["decisives"] = result["tm_goals"] + result["tm_assists"] + result["gk_clean_sheet"].astype(float)
    result["player_sofascore_match_found"] = result.get(
        "player_sofascore_match_found",
        pd.Series(False, index=result.index),
    ).astype(str).str.casefold().eq("true")
    result["sofa_player_minutes"] = result.get("player_sofascore_minutes_played", pd.Series(0, index=result.index)).fillna(0)
    result["is_substitute"] = result.get(
        "player_sofascore_substitute",
        pd.Series(False, index=result.index),
    ).astype(str).str.casefold().eq("true")
    result["bench_minutes"] = result["sofa_player_minutes"].fillna(result["tm_minutes"]).fillna(0)
    result["is_bench_played"] = (
        ~result["is_dnp"]
        & (result["is_bench"] | result["is_substitute"])
        & result["bench_minutes"].gt(0)
    )
    result["sofa_player_goals"] = result.get("player_goals", pd.Series(0, index=result.index)).fillna(0)
    result["sofa_player_assists"] = result.get("player_goal_assist", pd.Series(0, index=result.index)).fillna(0)
    result["sofa_player_xg"] = result.get("player_expected_goals", pd.Series(0, index=result.index)).fillna(0)
    result["competition"] = result.get("transfermarkt_Competition", "").fillna("").astype(str)
    result["season"] = result.get("transfermarkt_Season", "").fillna("").astype(str)
    result["game_date_key"] = result["Game Date"].dt.strftime("%Y-%m-%d")
    result["club_date_key"] = result.get("Club Slug", "").astype(str) + "||" + result["game_date_key"].fillna("")
    result["tm_matchday_covered"] = result.groupby("club_date_key")["tm_in_matchday_squad"].transform("any")
    result["score_band"] = result.apply(_score_band, axis=1)
    return result


def _prepare_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    result["game_date"] = pd.to_datetime(result.get("game_date"), errors="coerce")
    numeric_columns = [
        "sorare_score_real",
        "decisive_score_f",
        "all_around_score_f",
        "all_around_score_used_f",
        "score_f_raw",
        "score_f",
        "score_diff",
        "score_abs_diff",
    ]
    point_columns = [column for column in result.columns if column.startswith("points_") or column.startswith("weight_")]
    return _to_numeric(result, numeric_columns + point_columns)


def _prepare_teams(df: pd.DataFrame) -> pd.DataFrame:
    numeric_columns = [
        "avg_gw_points",
        "avg_score_per_player",
        "clean_sheets",
        "consistency",
        "total_players",
        "avg_minutes",
        "avg_decisive_actions",
        "avg_sofascore_xg",
        "avg_sofascore_possession",
        "avg_sofascore_total_shots",
        "avg_sofascore_shots_on_target",
        "avg_sofascore_corner_kicks",
    ]
    return _to_numeric(df, numeric_columns)


def _prepare_match_stats(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    text_columns = {"_match_key", "home_team", "away_team", "is_home", "status", "error", "lookup_error"}
    numeric_columns = [column for column in df.columns if column not in text_columns]
    return _to_numeric(df, numeric_columns)


MAIN_DF = _prepare_main(_load_csv(MAIN_PATH))
SCORE_BREAKDOWN_DF = _prepare_breakdown(_load_csv(SCORE_BREAKDOWN_PATH))
TEAM_DF = _prepare_teams(_load_csv(TEAM_PATH))
MATCH_DF = _prepare_match_stats(_load_csv(MATCH_STATS_PATH))
SCORING_MATRIX_WEIGHTS = _load_scoring_matrix(SCORING_MATRIX_PATH)


def _filter_main_rows(search: str, club: str, competition: str, position: str, season: str) -> pd.DataFrame:
    df = MAIN_DF.copy()
    df = _filter_text(df, search, ["Player", "Player Slug", "Club", "sofascore_home_team", "sofascore_away_team"])
    if club != "All" and "Club" in df.columns:
        df = df[df["Club"].astype(str) == club]
    if competition != "All" and "competition" in df.columns:
        df = df[df["competition"].astype(str) == competition]
    if position != "All" and "Position" in df.columns:
        df = df[df["Position"].astype(str) == position]
    if season != "All" and "season" in df.columns:
        df = df[df["season"].astype(str) == season]
    return df


def player_profile(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Players",
        "Club",
        "Position",
        "minutes_played",
        "appearances",
        "starter",
        "bench",
        "avg_score",
        "decisives",
        "sofascore_matches",
        "sofascore_minutes",
        "avg_sofascore_rating",
        "sofascore_goals",
        "sofascore_assists",
        "sofascore_xg",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    work = df.copy()
    work["appearance_score"] = work["Score"].where(work["tm_in_matchday_squad"])
    grouped = work.groupby(["Player", "Club", "Position"], dropna=False)
    profile = grouped.agg(
        minutes_played=("tm_minutes", "sum"),
        appearances=("tm_in_matchday_squad", "sum"),
        starter=("is_starter", "sum"),
        bench=("is_bench", "sum"),
        avg_score=("appearance_score", "mean"),
        decisives=("decisives", "sum"),
        sofascore_matches=("player_sofascore_match_found", "sum"),
        sofascore_minutes=("sofa_player_minutes", "sum"),
        avg_sofascore_rating=("player_sofascore_rating", "mean"),
        sofascore_goals=("sofa_player_goals", "sum"),
        sofascore_assists=("sofa_player_assists", "sum"),
        sofascore_xg=("sofa_player_xg", "sum"),
    ).reset_index()
    profile = profile.rename(columns={"Player": "Players"})
    profile = profile[columns]
    numeric = profile.select_dtypes(include="number").columns
    profile[numeric] = profile[numeric].round(2)
    return profile.sort_values(["avg_score", "starter"], ascending=[False, False]).head(250)


def player_table(search: str, club: str, competition: str, position: str, season: str) -> pd.DataFrame:
    return player_profile(_filter_main_rows(search, club, competition, position, season))


def selected_player_summary(player: str) -> pd.DataFrame:
    columns = [
        "Player",
        "max_score",
        "min_score",
        "avg_score",
        "avg_score_starter",
        "avg_score_bench",
        "avg_score_p90",
        "avg_score_with_decisive",
        "avg_score_no_decisive",
        "sofascore_matches",
        "avg_sofascore_rating",
        "sofascore_minutes",
        "sofascore_goals",
        "sofascore_assists",
        "sofascore_xg",
    ]
    if not player or MAIN_DF.empty:
        return pd.DataFrame(columns=columns)

    df = MAIN_DF[MAIN_DF["Player"].astype(str) == str(player)].copy()
    appearances = df[df["tm_in_matchday_squad"]].copy()
    if appearances.empty:
        return pd.DataFrame([{column: "" for column in columns} | {"Player": player}])

    total_minutes = appearances["tm_minutes"].fillna(0).sum()
    starter_scores = appearances.loc[appearances["is_starter"], "Score"]
    bench_scores = df.loc[df["is_bench_played"], "Score"]
    decisive_scores = appearances.loc[appearances["decisives"].fillna(0).gt(0), "Score"]
    no_decisive_scores = appearances.loc[appearances["decisives"].fillna(0).eq(0), "Score"]
    total_score = appearances["Score"].sum()
    sofa_rows = df[df["player_sofascore_match_found"]].copy()

    summary = pd.DataFrame(
        [
            {
                "Player": player,
                "max_score": appearances["Score"].max(),
                "min_score": appearances["Score"].min(),
                "avg_score": appearances["Score"].mean(),
                "avg_score_starter": starter_scores.mean(),
                "avg_score_bench": bench_scores.mean(),
                "avg_score_p90": (total_score / total_minutes * 90) if total_minutes else pd.NA,
                "avg_score_with_decisive": decisive_scores.mean(),
                "avg_score_no_decisive": no_decisive_scores.mean(),
                "sofascore_matches": len(sofa_rows),
                "avg_sofascore_rating": sofa_rows["player_sofascore_rating"].mean(),
                "sofascore_minutes": sofa_rows["sofa_player_minutes"].sum(),
                "sofascore_goals": sofa_rows["sofa_player_goals"].sum(),
                "sofascore_assists": sofa_rows["sofa_player_assists"].sum(),
                "sofascore_xg": sofa_rows["sofa_player_xg"].sum(),
            }
        ]
    )
    numeric = summary.select_dtypes(include="number").columns
    summary[numeric] = summary[numeric].round(2)
    return summary[columns]


def selected_player_rows(player: str) -> pd.DataFrame:
    columns = [
        "Game Date",
        "Club",
        "Position",
        "Score",
        "score_band",
        "transfermarkt_LineupStatus",
        "transfermarkt_TMMinutesPlayed",
        "transfermarkt_TMGoals",
        "transfermarkt_TMAssists",
        "player_sofascore_match_found",
        "player_sofascore_match_source",
        "player_sofascore_rating",
        "player_sofascore_minutes_played",
        "player_goals",
        "player_goal_assist",
        "player_expected_goals",
        "player_expected_assists",
        "player_total_shots",
        "player_on_target_scoring_attempt",
        "player_key_pass",
        "player_total_pass",
        "player_accurate_pass",
        "player_duel_won",
        "player_total_tackle",
        "player_interception_won",
        "player_total_clearance",
        "player_ball_recovery",
        "player_saves",
        "player_goals_prevented",
        "sofascore_home_team",
        "sofascore_away_team",
        "transfermarkt_Competition",
        "transfermarkt_RestDays",
        "sofascore_expected_goals_value",
        "sofascore_total_shots_value",
        "sofascore_shots_on_target_value",
    ]
    if not player or MAIN_DF.empty:
        return pd.DataFrame(columns=columns)
    df = MAIN_DF[MAIN_DF["Player"].astype(str) == str(player)].copy()
    df = df.sort_values("Game Date", ascending=False)
    return df[[column for column in columns if column in df.columns]].head(100)


def player_score_by_gameweek(player: str):
    empty = pd.DataFrame({"Game Date": [], "plot_score": [], "score_band": []})
    if not player or MAIN_DF.empty:
        return px.bar(empty, x="Game Date", y="plot_score", color="score_band", title="Player score by gameweek")
    df = MAIN_DF[MAIN_DF["Player"].astype(str) == str(player)].copy().sort_values("Game Date")
    if df.empty:
        return px.bar(empty, x="Game Date", y="plot_score", color="score_band", title=f"{player} score by gameweek")
    df["plot_score"] = df["Score"].where(~df["is_dnp"], 3.0)
    fig = px.bar(
        df,
        x="Game Date",
        y="plot_score",
        color="score_band",
        category_orders={"score_band": SCORE_BAND_ORDER},
        color_discrete_map=SCORE_BAND_COLORS,
        labels={
            "Game Date": "Game Date",
            "plot_score": "Score",
            "score_band": "Score",
        },
        hover_data={
            "Game Date": True,
            "Score": ":.1f",
            "plot_score": False,
            "score_band": True,
            "transfermarkt_LineupStatus": True,
            "transfermarkt_TMMinutesPlayed": True,
        },
        title=f"{player} score by gameweek",
    )
    fig.update_yaxes(range=[0, 105])
    fig.update_xaxes(title="Game Date", tickformat="%b %Y")
    fig.update_layout(
        bargap=0.2,
        legend_title_text="Score",
        plot_bgcolor="#e5ecf6",
        paper_bgcolor="white",
        margin=dict(l=60, r=30, t=45, b=45),
    )
    return fig


def _position_key(position: object) -> str:
    value = str(position or "").casefold()
    if "goalkeeper" in value or value in {"g", "gk"}:
        return "GK"
    if "defender" in value or value == "d":
        return "DEF"
    if "midfielder" in value or value == "m":
        return "MID"
    if "forward" in value or value == "f":
        return "FWD"
    return "FWD"


def _num_value(row: pd.Series, column: str) -> float:
    if not column or column not in row.index:
        return 0.0
    value = pd.to_numeric(row.get(column), errors="coerce")
    if pd.isna(value):
        return 0.0
    return float(value)


def _format_number(value: object) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return ""
    if float(number).is_integer():
        return str(int(number))
    return f"{float(number):.2f}".rstrip("0").rstrip(".")


def _score_breakdown_base_rows(
    player: str,
    season: str,
    tournament: str,
    team: str,
    position: str,
    min_minutes: float,
    starter_filter: str,
) -> pd.DataFrame:
    df = MAIN_DF.copy()
    if "player_sofascore_match_found" in df.columns:
        df = df[df["player_sofascore_match_found"]]
    if player:
        df = df[df["Player"].astype(str) == str(player)]
    if season != "All" and "player_sofascore_season" in df.columns:
        df = df[df["player_sofascore_season"].astype(str) == season]
    if tournament != "All" and "player_sofascore_tournament" in df.columns:
        df = df[df["player_sofascore_tournament"].astype(str) == tournament]
    if team != "All" and "player_sofascore_player_team" in df.columns:
        df = df[df["player_sofascore_player_team"].astype(str) == team]
    if position != "All" and "Position" in df.columns:
        df = df[df["Position"].astype(str) == position]
    if "player_sofascore_minutes_played" in df.columns:
        df = df[df["player_sofascore_minutes_played"].fillna(0) >= float(min_minutes or 0)]
    if starter_filter == "Starter":
        df = df[df.get("player_sofascore_starter", pd.Series(False, index=df.index)).astype(str).str.casefold().eq("true")]
    elif starter_filter == "Substitute":
        df = df[df.get("player_sofascore_substitute", pd.Series(False, index=df.index)).astype(str).str.casefold().eq("true")]
    elif starter_filter == "Played from bench":
        df = df[
            df.get("player_sofascore_substitute", pd.Series(False, index=df.index)).astype(str).str.casefold().eq("true")
            & df.get("player_sofascore_minutes_played", pd.Series(0, index=df.index)).fillna(0).gt(0)
        ]
    return df


def _match_label(row: pd.Series) -> str:
    date = pd.to_datetime(row.get("Game Date"), errors="coerce")
    date_label = date.strftime("%Y-%m-%d") if pd.notna(date) else str(row.get("Game Date", ""))[:10]
    home = row.get("player_sofascore_home_team") or row.get("sofascore_home_team") or ""
    away = row.get("player_sofascore_away_team") or row.get("sofascore_away_team") or ""
    tournament = row.get("player_sofascore_tournament") or row.get("transfermarkt_Competition") or ""
    slug = row.get("player_sofascore_event_slug") or row.get("sofascore_event_id") or ""
    return f"{date_label} | {home} vs {away} | {tournament} | {slug}"


def score_breakdown_match_dropdown(
    player: str,
    season: str,
    tournament: str,
    team: str,
    position: str,
    min_minutes: float,
    starter_filter: str,
):
    choices, value = _score_breakdown_match_choices(
        player,
        season,
        tournament,
        team,
        position,
        min_minutes,
        starter_filter,
    )
    return gr.update(choices=choices, value=value)


def _score_breakdown_match_choices(
    player: str,
    season: str,
    tournament: str,
    team: str,
    position: str,
    min_minutes: float,
    starter_filter: str,
) -> tuple[list[tuple[str, str]], str | None]:
    df = _score_breakdown_base_rows(player, season, tournament, team, position, min_minutes, starter_filter)
    df = df.sort_values("Game Date", ascending=False).head(300)
    choices = [(_match_label(row), str(index)) for index, row in df.iterrows()]
    value = choices[0][1] if choices else None
    return choices, value


def update_score_breakdown_after_filters(
    player: str,
    scope: str,
    season: str,
    tournament: str,
    team: str,
    position: str,
    min_minutes: float,
    starter_filter: str,
    show_only_mapped: bool,
    show_unmapped: bool,
):
    choices, row_id = _score_breakdown_match_choices(
        player,
        season,
        tournament,
        team,
        position,
        min_minutes,
        starter_filter,
    )
    return (
        gr.update(choices=choices, value=row_id),
        score_breakdown_kpis(row_id, player, scope, season, tournament, team, position, min_minutes, starter_filter, show_only_mapped, show_unmapped),
        score_breakdown_summary(row_id, player, scope, season, tournament, team, position, min_minutes, starter_filter, show_only_mapped, show_unmapped),
        score_breakdown_table(row_id, player, scope, season, tournament, team, position, min_minutes, starter_filter, show_only_mapped, show_unmapped),
        original_sofascore_stats(row_id, player, scope, season, tournament, team, position, min_minutes, starter_filter, show_only_mapped, show_unmapped),
    )


def _selected_score_breakdown_row(row_id: str, player: str = "") -> pd.Series | None:
    if row_id not in (None, ""):
        try:
            index = int(row_id)
            if index in MAIN_DF.index:
                return MAIN_DF.loc[index]
        except (TypeError, ValueError):
            pass
    df = _score_breakdown_base_rows(player, "All", "All", "All", "All", 0, "All")
    if df.empty:
        return None
    return df.sort_values("Game Date", ascending=False).iloc[0]


def _score_breakdown_rows_for_scope(
    row_id: str,
    player: str,
    scope: str,
    season: str,
    tournament: str,
    team: str,
    position: str,
    min_minutes: float,
    starter_filter: str,
) -> pd.DataFrame:
    if scope == "All-time":
        df = MAIN_DF.copy()
        if "player_sofascore_match_found" in df.columns:
            df = df[df["player_sofascore_match_found"]]
        if player:
            df = df[df["Player"].astype(str) == str(player)]
        if position != "All" and "Position" in df.columns:
            df = df[df["Position"].astype(str) == position]
        return df.sort_values("Game Date", ascending=False)

    if scope == "Filtered average":
        return _score_breakdown_base_rows(player, season, tournament, team, position, min_minutes, starter_filter).sort_values(
            "Game Date",
            ascending=False,
        )

    row = _selected_score_breakdown_row(row_id, player)
    if row is None:
        return pd.DataFrame()
    return pd.DataFrame([row])


def _aggregate_score_breakdown_rows(
    player: str,
    scope: str,
    season: str,
    tournament: str,
    team: str,
    position: str,
    min_minutes: float,
    starter_filter: str,
) -> pd.DataFrame:
    if scope == "All-time":
        df = MAIN_DF.copy()
        if "player_sofascore_match_found" in df.columns:
            df = df[df["player_sofascore_match_found"]]
        if player:
            df = df[df["Player"].astype(str) == str(player)]
        if position != "All" and "Position" in df.columns:
            df = df[df["Position"].astype(str) == position]
        return df.sort_values("Game Date", ascending=False)

    return _score_breakdown_base_rows(player, season, tournament, team, position, min_minutes, starter_filter).sort_values(
        "Game Date",
        ascending=False,
    )


def _decisive_quantities(row: pd.Series) -> tuple[float, float, int, float]:
    positive = 0.0
    negative = 0.0
    for config in SORARE_SCORING_MATRIX.values():
        scoring_type = config.get("scoring_type")
        if scoring_type not in {"decisive_positive", "decisive_negative"}:
            continue
        quantity = _num_value(row, config["main_column"])
        if scoring_type == "decisive_positive":
            positive += quantity
        else:
            negative += quantity
    level = max(-3, min(5, int(positive - negative)))
    return positive, negative, level, float(DECISIVE_LEVEL_POINTS[level])


def _matrix_points_per_action(config: dict[str, object], position_key: str) -> float | None:
    matrix_stat = MATRIX_STAT_BY_MAIN_COLUMN.get(str(config.get("main_column", "")))
    if matrix_stat and matrix_stat in SCORING_MATRIX_WEIGHTS:
        return SCORING_MATRIX_WEIGHTS[matrix_stat].get(position_key)

    points = config.get("points")
    if isinstance(points, dict):
        return points.get(position_key)
    if points in (None, ""):
        return None
    return float(points)


def _build_score_breakdown(
    data: pd.Series | pd.DataFrame | None,
    show_only_mapped: bool,
    show_unmapped: bool,
    scope: str = "Selected match",
) -> pd.DataFrame:
    columns = [
        "Category",
        "SofaScore stat column",
        "Display stat name",
        "Raw SofaScore value",
        "Sorare action name",
        "Sorare scoring type",
        "Sorare points per action",
        "Quantity",
        "Total Sorare points impact",
        "Positive / Negative / Neutral",
        "Notes",
    ]
    if data is None or (isinstance(data, pd.DataFrame) and data.empty):
        return pd.DataFrame(columns=columns)

    rows_df = pd.DataFrame([data]) if isinstance(data, pd.Series) else data.copy()
    is_average = scope == "Filtered average"
    is_aggregate = len(rows_df) > 1 or scope in {"Filtered average", "All-time"}
    display_count = max(len(rows_df), 1)
    mapped_sofa_columns = {config["sofascore_column"] for config in SORARE_SCORING_MATRIX.values()}
    include_unmapped = bool(show_unmapped) and not bool(show_only_mapped)
    rows = []

    for config in SORARE_SCORING_MATRIX.values():
        scoring_type = config["scoring_type"]
        is_mapped = scoring_type != "not_mapped"
        if not is_mapped and not include_unmapped:
            continue

        row_quantities = []
        row_points = []
        point_labels = set()
        applies_count = 0
        for _, match_row in rows_df.iterrows():
            position_key = _position_key(match_row.get("Position"))
            if position_key not in config.get("applies_to_positions", []):
                row_quantities.append(0.0)
                row_points.append(0.0)
                continue
            applies_count += 1
            quantity = _num_value(match_row, config["main_column"])
            points_per_action = _matrix_points_per_action(config, position_key)
            row_quantities.append(quantity)
            if points_per_action not in (None, ""):
                point_labels.add(_format_number(points_per_action))
                row_points.append(quantity * float(points_per_action))
            else:
                row_points.append(0.0)

        if applies_count == 0:
            continue

        quantity = sum(row_quantities) / display_count if is_average else sum(row_quantities)
        total_points = sum(row_points) / display_count if is_average else sum(row_points)
        points_per_action = ", ".join(sorted(point_labels)) if point_labels else ""

        if scoring_type == "decisive_positive":
            points_label = "+1 DS level"
            total_impact = f"+{_format_number(quantity)} DS level{' avg' if is_average else ''}" if quantity else ""
            polarity = "Positive" if quantity else "Neutral"
            scoring_label = "Decisive"
        elif scoring_type == "decisive_negative":
            points_label = "-1 DS level"
            total_impact = f"-{_format_number(quantity)} DS level{' avg' if is_average else ''}" if quantity else ""
            polarity = "Negative" if quantity else "Neutral"
            scoring_label = "Decisive"
        elif scoring_type == "not_mapped" or points_per_action == "":
            points_label = ""
            total_impact = ""
            polarity = "Neutral"
            scoring_label = "Not mapped"
        else:
            points_label = points_per_action
            total_impact = _format_number(total_points)
            polarity = "Positive" if total_points > 0 else ("Negative" if total_points < 0 else "Neutral")
            scoring_label = "All-Around"

        rows.append(
            {
                "Category": config["category"],
                "SofaScore stat column": config["sofascore_column"],
                "Display stat name": config["sofascore_column"].replace("_", " ").title(),
                "Raw SofaScore value": _format_number(quantity),
                "Sorare action name": config["sorare_action"],
                "Sorare scoring type": scoring_label,
                "Sorare points per action": points_label,
                "Quantity": _format_number(quantity),
                "Total Sorare points impact": total_impact,
                "Positive / Negative / Neutral": polarity,
                "Notes": config.get("notes", ""),
            }
        )

    if include_unmapped:
        for sofa_column in SOFASCORE_RAW_STAT_COLUMNS:
            if sofa_column in mapped_sofa_columns:
                continue
            main_column = f"player_{sofa_column}"
            if main_column not in rows_df.columns:
                continue
            quantities = [_num_value(match_row, main_column) for _, match_row in rows_df.iterrows()]
            quantity = sum(quantities) / display_count if is_average else sum(quantities)
            rows.append(
                {
                    "Category": "SofaScore",
                    "SofaScore stat column": sofa_column,
                    "Display stat name": sofa_column.replace("_", " ").title(),
                    "Raw SofaScore value": _format_number(quantity),
                    "Sorare action name": "",
                    "Sorare scoring type": "Not mapped",
                    "Sorare points per action": "",
                    "Quantity": _format_number(quantity),
                    "Total Sorare points impact": "",
                    "Positive / Negative / Neutral": "Neutral",
                    "Notes": "Available SofaScore stat with no mapped Sorare scoring action in this project config.",
                }
            )

    result = pd.DataFrame(rows, columns=columns)
    if is_aggregate and not result.empty:
        label = "Average per match" if is_average else "All-time total"
        result["Notes"] = result["Notes"].astype(str) + " " + label + f" across {len(rows_df)} match rows."
    return result


def _single_row_score_metrics(row: pd.Series) -> dict[str, float]:
    breakdown = _build_score_breakdown(row, show_only_mapped=True, show_unmapped=False)
    point_values = pd.to_numeric(breakdown["Total Sorare points impact"], errors="coerce")
    all_around = float(point_values.fillna(0).sum())
    _, _, decisive_level, decisive_score = _decisive_quantities(row)
    all_around_used = 0.0 if decisive_level >= 0 and all_around < 0 else all_around
    estimated_score = max(0.0, min(100.0, decisive_score + all_around_used))
    return {
        "estimated_score": estimated_score,
        "decisive_level": float(decisive_level),
        "decisive_score": decisive_score,
        "all_around": all_around,
        "sorare_score": _num_value(row, "Score"),
        "sofascore_rating": _num_value(row, "player_sofascore_rating"),
    }


def _score_breakdown_metrics(data: pd.Series | pd.DataFrame | None, breakdown: pd.DataFrame, scope: str = "Selected match") -> dict[str, object]:
    if data is None or (isinstance(data, pd.DataFrame) and data.empty):
        return {
            "estimated_score": 0.0,
            "decisive_level": "",
            "decisive_score": 0.0,
            "all_around": 0.0,
            "positive_points": 0.0,
            "negative_points": 0.0,
            "mapped_actions": 0,
            "unmapped_actions": 0,
            "rating_difference": "",
            "sorare_score": "",
            "match_count": 0,
            "minutes": 0.0,
            "rating": "",
        }

    rows_df = pd.DataFrame([data]) if isinstance(data, pd.Series) else data.copy()
    point_values = pd.to_numeric(breakdown["Total Sorare points impact"], errors="coerce")
    positive_points = float(point_values[point_values > 0].sum())
    negative_points = float(point_values[point_values < 0].sum())
    all_around = float(point_values.fillna(0).sum())

    per_match = [_single_row_score_metrics(match_row) for _, match_row in rows_df.iterrows()]
    metric_df = pd.DataFrame(per_match)
    if scope == "All-time":
        estimated_score = float(metric_df["estimated_score"].sum())
        decisive_score = float(metric_df["decisive_score"].sum())
        decisive_level = _format_number(metric_df["decisive_level"].sum())
        sorare_score = float(metric_df["sorare_score"].sum())
        rating = float(metric_df["sofascore_rating"].mean()) if not metric_df.empty else 0.0
        rating_difference = float(metric_df["estimated_score"].mean() - metric_df["sofascore_rating"].mean()) if not metric_df.empty else ""
    else:
        estimated_score = float(metric_df["estimated_score"].mean())
        decisive_score = float(metric_df["decisive_score"].mean())
        decisive_level = _format_number(metric_df["decisive_level"].mean())
        sorare_score = float(metric_df["sorare_score"].mean())
        rating = float(metric_df["sofascore_rating"].mean()) if not metric_df.empty else 0.0
        rating_difference = estimated_score - rating if rating else ""

    return {
        "estimated_score": estimated_score,
        "decisive_level": decisive_level,
        "decisive_score": decisive_score,
        "all_around": all_around,
        "positive_points": positive_points,
        "negative_points": negative_points,
        "mapped_actions": int((breakdown["Sorare scoring type"] != "Not mapped").sum()),
        "unmapped_actions": int((breakdown["Sorare scoring type"] == "Not mapped").sum()),
        "rating_difference": rating_difference,
        "sorare_score": sorare_score,
        "match_count": len(rows_df),
        "minutes": float(rows_df.get("player_sofascore_minutes_played", pd.Series(0, index=rows_df.index)).fillna(0).sum()),
        "rating": rating,
    }


def score_breakdown_kpis(
    row_id: str,
    player: str,
    scope: str,
    season: str,
    tournament: str,
    team: str,
    position: str,
    min_minutes: float,
    starter_filter: str,
    show_only_mapped: bool,
    show_unmapped: bool,
) -> str:
    rows_df = _score_breakdown_rows_for_scope(row_id, player, scope, season, tournament, team, position, min_minutes, starter_filter)
    breakdown = _build_score_breakdown(rows_df, show_only_mapped, show_unmapped, scope)
    metrics = _score_breakdown_metrics(rows_df, breakdown, scope)
    if rows_df.empty:
        return "<div>No player-match rows selected.</div>"

    row = rows_df.iloc[0]
    score_label = "Total Sorare Score" if scope == "All-time" else "Avg Sorare Score" if scope == "Filtered average" else "Sorare Score"
    estimated_label = "Total estimated Sorare Score" if scope == "All-time" else "Avg estimated Sorare Score" if scope == "Filtered average" else "Estimated Sorare Score"
    card_values = [
        ("Scope", scope),
        ("Player name", row.get("Player", "")),
        ("Team", row.get("player_sofascore_player_team", "")),
        ("Position", row.get("Position", "")),
        ("Matches", metrics["match_count"]),
        ("Minutes played", _format_number(metrics["minutes"])),
        ("Avg SofaScore rating", _format_number(metrics["rating"])),
        (score_label, _format_number(metrics["sorare_score"])),
        (estimated_label, _format_number(metrics["estimated_score"])),
        ("Estimated DS level", metrics["decisive_level"]),
        ("Estimated All-Around", _format_number(metrics["all_around"])),
        ("Positive Sorare points", _format_number(metrics["positive_points"])),
        ("Negative Sorare points", _format_number(metrics["negative_points"])),
        ("Mapped actions", metrics["mapped_actions"]),
        ("Unmapped SofaScore actions", metrics["unmapped_actions"]),
        ("Sorare impact minus SofaScore rating", _format_number(metrics["rating_difference"])),
    ]
    cards = "".join(
        f"<div style='border:1px solid #d9e2ec;border-radius:6px;padding:10px;background:#fff;'>"
        f"<div style='font-size:12px;color:#64748b;'>{label}</div>"
        f"<div style='font-size:18px;font-weight:700;color:#0f172a;'>{value}</div>"
        f"</div>"
        for label, value in card_values
    )
    return f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;'>{cards}</div>"


def score_breakdown_table(
    row_id: str,
    player: str,
    scope: str,
    season: str,
    tournament: str,
    team: str,
    position: str,
    min_minutes: float,
    starter_filter: str,
    show_only_mapped: bool,
    show_unmapped: bool,
) -> pd.DataFrame:
    rows_df = _score_breakdown_rows_for_scope(row_id, player, scope, season, tournament, team, position, min_minutes, starter_filter)
    return _build_score_breakdown(rows_df, show_only_mapped, show_unmapped, scope)


def original_sofascore_stats(
    row_id: str,
    player: str,
    scope: str,
    season: str,
    tournament: str,
    team: str,
    position: str,
    min_minutes: float,
    starter_filter: str,
    show_only_mapped: bool,
    show_unmapped: bool,
) -> pd.DataFrame:
    rows_df = _score_breakdown_rows_for_scope(row_id, player, scope, season, tournament, team, position, min_minutes, starter_filter)
    columns = ["SofaScore stat column", "Raw SofaScore value", "Mapped to Sorare", "Sorare action name"]
    if rows_df.empty:
        return pd.DataFrame(columns=columns)

    mapped_lookup = {
        config["sofascore_column"]: config
        for config in SORARE_SCORING_MATRIX.values()
    }
    include_unmapped = bool(show_unmapped) and not bool(show_only_mapped)
    is_average = scope == "Filtered average"
    display_count = max(len(rows_df), 1)
    rows = []
    for sofa_column in SOFASCORE_RAW_STAT_COLUMNS:
        main_column = f"player_{sofa_column}"
        if main_column not in rows_df.columns:
            continue
        config = mapped_lookup.get(sofa_column)
        is_mapped = bool(config and config.get("scoring_type") != "not_mapped")
        if not is_mapped and not include_unmapped:
            continue
        quantity = sum(_num_value(match_row, main_column) for _, match_row in rows_df.iterrows())
        if is_average:
            quantity = quantity / display_count
        rows.append(
            {
                "SofaScore stat column": sofa_column,
                "Raw SofaScore value": _format_number(quantity),
                "Mapped to Sorare": "Yes" if is_mapped else "No",
                "Sorare action name": config.get("sorare_action", "") if config else "",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def score_breakdown_summary(
    row_id: str,
    player: str,
    scope: str,
    season: str,
    tournament: str,
    team: str,
    position: str,
    min_minutes: float,
    starter_filter: str,
    show_only_mapped: bool,
    show_unmapped: bool,
) -> pd.DataFrame:
    rows_df = _score_breakdown_rows_for_scope(row_id, player, scope, season, tournament, team, position, min_minutes, starter_filter)
    breakdown = _build_score_breakdown(rows_df, show_only_mapped, show_unmapped, scope)
    metrics = _score_breakdown_metrics(rows_df, breakdown, scope)
    if rows_df.empty:
        return pd.DataFrame(columns=["Metric", "Value"])
    score_label = "Total Sorare Score" if scope == "All-time" else "Average Sorare Score" if scope == "Filtered average" else "Sorare Score"
    return pd.DataFrame(
        [
            {"Metric": "Rows in scope", "Value": _format_number(metrics["match_count"])},
            {"Metric": score_label, "Value": _format_number(metrics["sorare_score"])},
            {"Metric": "Estimated Sorare Decisive Score contribution", "Value": _format_number(metrics["decisive_score"])},
            {"Metric": "Estimated Sorare All-Around contribution", "Value": _format_number(metrics["all_around"])},
            {"Metric": "Estimated Sorare Score", "Value": _format_number(metrics["estimated_score"])},
            {"Metric": "Average SofaScore rating", "Value": _format_number(metrics["rating"])},
            {"Metric": "Difference: estimated Sorare impact - SofaScore rating", "Value": _format_number(metrics["rating_difference"])},
        ]
    )


def _category_raw_table(breakdown: pd.DataFrame, category: str) -> pd.DataFrame:
    columns = [
        "SofaScore stat column",
        "Display stat name",
        "Raw SofaScore value",
        "Sorare action name",
        "Notes",
    ]
    if breakdown.empty:
        return pd.DataFrame(columns=columns)
    data = breakdown[breakdown["Category"].eq(category)].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)
    return data[columns].reset_index(drop=True)


def _category_score_table(
    breakdown: pd.DataFrame,
    category: str,
    metrics: dict[str, object] | None = None,
    scope: str = "Filtered average",
) -> pd.DataFrame:
    columns = [
        "Sorare action name",
        "Sorare scoring type",
        "Sorare points per action",
        "Quantity",
        "Total Sorare points impact",
        "Positive / Negative / Neutral",
        "Notes",
    ]
    if breakdown.empty:
        return pd.DataFrame(columns=columns)
    data = breakdown[breakdown["Category"].eq(category)].copy()
    if data.empty:
        result = pd.DataFrame(columns=columns)
    else:
        result = data[columns].reset_index(drop=True)

    if category == "Decisive" and metrics:
        summary_row = pd.DataFrame(
            [
                {
                    "Sorare action name": "Estimated Decisive Score",
                    "Sorare scoring type": "Decisive Score",
                    "Sorare points per action": "",
                    "Quantity": metrics.get("decisive_level", ""),
                    "Total Sorare points impact": _format_number(metrics.get("decisive_score", "")),
                    "Positive / Negative / Neutral": "Neutral",
                    "Notes": "Average decisive score per match." if scope == "Filtered average" else "Total decisive score across selected player rows.",
                }
            ]
        )
        result = pd.concat([summary_row, result], ignore_index=True)
    return result


def update_aggregate_score_breakdown(
    player: str,
    scope: str,
    season: str,
    tournament: str,
    team: str,
    position: str,
    min_minutes: float,
    starter_filter: str,
):
    rows_df = _aggregate_score_breakdown_rows(player, scope, season, tournament, team, position, min_minutes, starter_filter)
    breakdown = _build_score_breakdown(rows_df, show_only_mapped=True, show_unmapped=False, scope=scope)
    metrics = _score_breakdown_metrics(rows_df, breakdown, scope)
    kpis = score_breakdown_kpis("", player, scope, season, tournament, team, position, min_minutes, starter_filter, True, False)
    summary = score_breakdown_summary("", player, scope, season, tournament, team, position, min_minutes, starter_filter, True, False)

    tables = []
    for _, _, category in CATEGORY_TABLES:
        tables.append(_category_raw_table(breakdown, category))
        tables.append(_category_score_table(breakdown, category, metrics, scope))
    return (kpis, summary, *tables)


def _legacy_filter_breakdown_rows(search: str, club: str, position: str) -> pd.DataFrame:
    df = SCORE_BREAKDOWN_DF.copy()
    df = _filter_text(df, search, ["player_name", "club", "match", "position"])
    if club != "All" and "club" in df.columns:
        df = df[df["club"].astype(str) == club]
    if position != "All" and "position" in df.columns:
        df = df[df["position"].astype(str) == position]
    return df


def legacy_score_breakdown_profile(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Players",
        "Club",
        "Position",
        "rows",
        "avg_actual_score",
        "avg_score_f",
        "avg_decisive_score",
        "avg_all_around",
        "mae_error",
        "avg_diff",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    grouped = df.groupby(["player_name", "club", "position"], dropna=False)
    profile = grouped.agg(
        rows=("player_name", "size"),
        avg_actual_score=("sorare_score_real", "mean"),
        avg_score_f=("score_f", "mean"),
        avg_decisive_score=("decisive_score_f", "mean"),
        avg_all_around=("all_around_score_f", "mean"),
        mae_error=("score_abs_diff", "mean"),
        avg_diff=("score_diff", "mean"),
    ).reset_index()
    profile = profile.rename(columns={"player_name": "Players", "club": "Club", "position": "Position"})
    numeric = profile.select_dtypes(include="number").columns
    profile[numeric] = profile[numeric].round(2)
    return profile[columns].sort_values("mae_error", ascending=False).head(250)


def legacy_score_breakdown_table(search: str, club: str, position: str) -> pd.DataFrame:
    return legacy_score_breakdown_profile(_legacy_filter_breakdown_rows(search, club, position))


def legacy_selected_breakdown_rows(player: str) -> pd.DataFrame:
    columns = [
        "game_date",
        "club",
        "match",
        "position",
        "lineup_status",
        "sorare_score_real",
        "score_f",
        "decisive_score_f",
        "all_around_score_f",
        "all_around_score_used_f",
        "score_diff",
        "score_abs_diff",
        "formula_note",
    ]
    if not player or SCORE_BREAKDOWN_DF.empty:
        return pd.DataFrame(columns=columns)
    df = SCORE_BREAKDOWN_DF[SCORE_BREAKDOWN_DF["player_name"].astype(str) == str(player)].copy()
    df = df.sort_values("game_date", ascending=False)
    return df[[column for column in columns if column in df.columns]].head(100)


def legacy_score_breakdown_history(player: str):
    empty = pd.DataFrame({"game_date": [], "Score type": [], "Score": []})
    if not player or SCORE_BREAKDOWN_DF.empty:
        return px.line(empty, x="game_date", y="Score", color="Score type", title="Score breakdown history")
    df = SCORE_BREAKDOWN_DF[SCORE_BREAKDOWN_DF["player_name"].astype(str) == str(player)].copy()
    if df.empty:
        return px.line(empty, x="game_date", y="Score", color="Score type", title=f"{player} score breakdown")
    df = df.sort_values("game_date")
    plot_cols = [
        column
        for column in ["sorare_score_real", "score_f", "decisive_score_f", "all_around_score_f"]
        if column in df.columns
    ]
    plot_df = df[["game_date"] + plot_cols].melt("game_date", var_name="Score type", value_name="Score")
    labels = {
        "sorare_score_real": "Actual Sorare",
        "score_f": "Formula score_f",
        "decisive_score_f": "Decisive",
        "all_around_score_f": "All-Around",
    }
    plot_df["Score type"] = plot_df["Score type"].map(labels).fillna(plot_df["Score type"])
    fig = px.line(plot_df, x="game_date", y="Score", color="Score type", markers=True, title=f"{player} score breakdown")
    fig.update_yaxes(range=[0, 105])
    return fig


def team_table(search: str) -> pd.DataFrame:
    df = _filter_text(TEAM_DF, search, ["team", "team_category"])
    return df.head(200)


def team_score_chart(df: pd.DataFrame):
    if df.empty or "avg_score_per_player" not in df.columns:
        return px.bar(pd.DataFrame({"team": [], "avg_score_per_player": []}), x="avg_score_per_player", y="team")
    data = df.sort_values("avg_score_per_player", ascending=True)
    return px.bar(data, x="avg_score_per_player", y="team", orientation="h", title="Teams by average player score")


def team_shot_scatter(df: pd.DataFrame):
    if df.empty:
        return px.scatter(pd.DataFrame({"avg_sofascore_xg": [], "avg_sofascore_total_shots": []}), x="avg_sofascore_xg", y="avg_sofascore_total_shots")
    return px.scatter(
        df,
        x="avg_sofascore_xg",
        y="avg_sofascore_total_shots",
        size="total_players" if "total_players" in df.columns else None,
        color="team_category" if "team_category" in df.columns else None,
        hover_name="team",
        title="Team attacking profile",
    )


def update_team_view(search: str):
    df = team_table(search)
    return df, team_score_chart(df), team_shot_scatter(df)


def match_table(search: str, status: str, min_confidence: float) -> pd.DataFrame:
    df = MATCH_DF.copy()
    df = _filter_text(df, search, ["home_team", "away_team", "_match_key"])
    if status != "All" and "status" in df.columns:
        df = df[df["status"].astype(str) == status]
    if "match_confidence" in df.columns:
        df = df[pd.to_numeric(df["match_confidence"], errors="coerce").fillna(0) >= min_confidence]
    columns = [
        "event_id",
        "_match_key",
        "home_team",
        "away_team",
        "is_home",
        "status",
        "match_confidence",
        "expected_goals_value",
        "total_shots_value",
        "shots_on_target_value",
        "corner_kicks_value",
        "ball_possession_value",
    ]
    return df[[column for column in columns if column in df.columns]].head(300)


def match_shots_chart(search: str, status: str, min_confidence: float):
    df = match_table(search, status, min_confidence)
    if df.empty or "total_shots_value" not in df.columns:
        return px.scatter(pd.DataFrame({"total_shots_value": [], "expected_goals_value": []}), x="total_shots_value", y="expected_goals_value")
    return px.scatter(
        df,
        x="total_shots_value",
        y="expected_goals_value" if "expected_goals_value" in df.columns else "shots_on_target_value",
        color="is_home" if "is_home" in df.columns else None,
        hover_data=[column for column in ["home_team", "away_team", "status"] if column in df.columns],
        title="Shot volume vs expected goals",
    )


def transfermarkt_coverage_table(search: str, club: str, season: str) -> pd.DataFrame:
    columns = [
        "Club",
        "season",
        "sorare_rows",
        "match_dates",
        "covered_match_dates",
        "coverage_pct",
        "players_in_tm_squad",
        "starters",
        "bench",
        "dnp",
        "tm_minutes",
        "tm_goals",
        "tm_assists",
        "latest_game_date",
    ]
    if MAIN_DF.empty:
        return pd.DataFrame(columns=columns)

    df = _filter_text(MAIN_DF.copy(), search, ["Club", "Player", "competition"])
    if club != "All" and "Club" in df.columns:
        df = df[df["Club"].astype(str) == club]
    if season != "All" and "season" in df.columns:
        df = df[df["season"].astype(str) == season]
    if df.empty:
        return pd.DataFrame(columns=columns)

    profile = df.groupby(["Club", "season"], dropna=False).agg(
        sorare_rows=("Player", "size"),
        match_dates=("game_date_key", "nunique"),
        covered_match_dates=("tm_matchday_covered", "sum"),
        players_in_tm_squad=("tm_in_matchday_squad", "sum"),
        starters=("is_starter", "sum"),
        bench=("is_bench", "sum"),
        dnp=("is_dnp", "sum"),
        tm_minutes=("tm_minutes", "sum"),
        tm_goals=("transfermarkt_TMGoals", "sum"),
        tm_assists=("transfermarkt_TMAssists", "sum"),
        latest_game_date=("Game Date", "max"),
    ).reset_index()
    covered_dates = (
        df[["Club", "season", "game_date_key", "tm_matchday_covered"]]
        .drop_duplicates()
        .groupby(["Club", "season"], dropna=False)["tm_matchday_covered"]
        .sum()
        .reset_index(name="covered_match_dates")
    )
    profile = profile.drop(columns=["covered_match_dates"]).merge(covered_dates, on=["Club", "season"], how="left")
    profile["coverage_pct"] = profile["covered_match_dates"].div(profile["match_dates"].replace(0, pd.NA)).mul(100)
    profile["latest_game_date"] = profile["latest_game_date"].dt.strftime("%Y-%m-%d")
    numeric = profile.select_dtypes(include="number").columns
    profile[numeric] = profile[numeric].round(2)
    return profile[columns].sort_values(["coverage_pct", "Club"], ascending=[True, True]).head(300)


def transfermarkt_missing_dates(search: str, club: str, season: str) -> pd.DataFrame:
    columns = ["Club", "season", "Game Date", "competition", "sorare_rows", "dnp_rows"]
    if MAIN_DF.empty:
        return pd.DataFrame(columns=columns)

    df = _filter_text(MAIN_DF.copy(), search, ["Club", "Player", "competition"])
    if club != "All" and "Club" in df.columns:
        df = df[df["Club"].astype(str) == club]
    if season != "All" and "season" in df.columns:
        df = df[df["season"].astype(str) == season]
    df = df[~df["tm_matchday_covered"]]
    if df.empty:
        return pd.DataFrame(columns=columns)

    missing = df.groupby(["Club", "season", "game_date_key", "competition"], dropna=False).agg(
        sorare_rows=("Player", "size"),
        dnp_rows=("is_dnp", "sum"),
    ).reset_index()
    missing = missing.rename(columns={"game_date_key": "Game Date"})
    return missing[columns].sort_values(["Club", "Game Date"], ascending=[True, False]).head(300)


def transfermarkt_coverage_chart(search: str, club: str, season: str):
    df = transfermarkt_coverage_table(search, club, season)
    if df.empty:
        return px.bar(pd.DataFrame({"Club": [], "coverage_pct": []}), x="coverage_pct", y="Club")
    data = df.sort_values("coverage_pct", ascending=True)
    return px.bar(
        data,
        x="coverage_pct",
        y="Club",
        color="season",
        orientation="h",
        hover_data=["match_dates", "covered_match_dates", "players_in_tm_squad"],
        title="Transfermarkt matchday coverage",
    )


def overview_metric_table() -> pd.DataFrame:
    tm_covered_dates = (
        MAIN_DF[["club_date_key", "tm_matchday_covered"]].drop_duplicates()["tm_matchday_covered"].sum()
        if {"club_date_key", "tm_matchday_covered"}.issubset(MAIN_DF.columns)
        else 0
    )
    tm_total_dates = (
        MAIN_DF["club_date_key"].nunique()
        if "club_date_key" in MAIN_DF.columns
        else 0
    )
    sofa_player_reviewed = (
        MAIN_DF.get("player_sofascore_review_matched", pd.Series(False, index=MAIN_DF.index))
        .astype(str)
        .str.casefold()
        .eq("true")
        .sum()
    )
    sofa_player_matched = (
        MAIN_DF.get("player_sofascore_match_found", pd.Series(False, index=MAIN_DF.index))
        .astype(str)
        .str.casefold()
        .eq("true")
        .sum()
    )
    return pd.DataFrame(
        [
            {"metric": "main rows", "value": f"{len(MAIN_DF):,}"},
            {"metric": "score breakdown rows", "value": f"{len(SCORE_BREAKDOWN_DF):,}"},
            {"metric": "teams", "value": f"{len(TEAM_DF):,}"},
            {"metric": "SofaScore team rows", "value": f"{len(MATCH_DF):,}"},
            {"metric": "avg Sorare score", "value": f"{MAIN_DF['Score'].mean():.2f}" if "Score" in MAIN_DF else ""},
            {"metric": "avg score_f", "value": f"{SCORE_BREAKDOWN_DF['score_f'].mean():.2f}" if "score_f" in SCORE_BREAKDOWN_DF else ""},
            {"metric": "TM covered club-dates", "value": f"{int(tm_covered_dates):,} / {tm_total_dates:,}"},
            {
                "metric": "TM coverage",
                "value": f"{(tm_covered_dates / tm_total_dates * 100):.1f}%" if tm_total_dates else "",
            },
            {"metric": "SofaScore reviewed player rows", "value": f"{int(sofa_player_reviewed):,}"},
            {"metric": "SofaScore player stat rows", "value": f"{int(sofa_player_matched):,}"},
            {
                "metric": "SofaScore player stat coverage",
                "value": f"{(sofa_player_matched / sofa_player_reviewed * 100):.1f}%" if sofa_player_reviewed else "",
            },
        ]
    )


def build_dashboard() -> gr.Blocks:
    club_choices = _choices(MAIN_DF, "Club")
    competition_choices = _choices(MAIN_DF, "competition")
    position_choices = _choices(MAIN_DF, "Position")
    season_choices = _choices(MAIN_DF, "season")
    player_choices = _choices(MAIN_DF, "Player", include_all=False)
    breakdown_player_choices = _choices(MAIN_DF[MAIN_DF.get("player_sofascore_match_found", False)], "Player", include_all=False)
    breakdown_season_choices = _choices(MAIN_DF, "player_sofascore_season")
    breakdown_tournament_choices = _choices(MAIN_DF, "player_sofascore_tournament")
    breakdown_team_choices = _choices(MAIN_DF, "player_sofascore_player_team")
    breakdown_position_choices = _choices(MAIN_DF, "Position")
    status_choices = _choices(MATCH_DF, "status")
    default_breakdown_player = breakdown_player_choices[0] if breakdown_player_choices else None
    initial_breakdown_outputs = update_aggregate_score_breakdown(
        default_breakdown_player or "",
        "Filtered average",
        "All",
        "All",
        "All",
        "All",
        0,
        "All",
    )

    with gr.Blocks(title="Sorare V4 Analytics Dashboard") as app:
        gr.Markdown("# Sorare V4 Analytics Dashboard")

        with gr.Tab("Overview"):
            with gr.Row():
                gr.Dataframe(value=overview_metric_table(), label="Dataset summary", interactive=False)
                gr.Plot(
                    value=px.histogram(MAIN_DF, x="Score", nbins=40, title="Sorare score distribution")
                    if not MAIN_DF.empty and "Score" in MAIN_DF.columns
                    else px.histogram(pd.DataFrame({"Score": []}), x="Score"),
                    label="Score distribution",
                )
            with gr.Row():
                gr.Plot(value=team_score_chart(TEAM_DF), label="Team score ranking")
                gr.Plot(
                    value=px.histogram(SCORE_BREAKDOWN_DF, x="score_abs_diff", nbins=40, title="score_f absolute error")
                    if not SCORE_BREAKDOWN_DF.empty and "score_abs_diff" in SCORE_BREAKDOWN_DF.columns
                    else px.histogram(pd.DataFrame({"score_abs_diff": []}), x="score_abs_diff"),
                    label="Formula error",
                )

        with gr.Tab("Players"):
            with gr.Row():
                player_search = gr.Textbox(label="Search players", placeholder="Player, club, team, or match")
                club_filter = gr.Dropdown(label="Club", choices=club_choices, value="All")
                competition_filter = gr.Dropdown(label="Competition", choices=competition_choices, value="All")
                position_filter = gr.Dropdown(label="Position", choices=position_choices, value="All")
                season_filter = gr.Dropdown(label="Season", choices=season_choices, value="All")
            players = gr.Dataframe(
                value=player_table("", "All", "All", "All", "All"),
                label="Player profiles",
                interactive=False,
                wrap=True,
            )
            selected_player = gr.Dropdown(label="Selected player", choices=player_choices)
            selected_player_summary_table = gr.Dataframe(
                value=selected_player_summary(""),
                label="Selected player summary",
                interactive=False,
                wrap=True,
            )
            player_plot = gr.Plot(label="Player score by gameweek")
            selected_player_table = gr.Dataframe(
                value=selected_player_rows(""),
                label="Selected player match rows",
                interactive=False,
                wrap=True,
            )

            for control in [player_search, club_filter, competition_filter, position_filter, season_filter]:
                control.change(
                    player_table,
                    inputs=[player_search, club_filter, competition_filter, position_filter, season_filter],
                    outputs=players,
                )
            selected_player.change(selected_player_summary, inputs=selected_player, outputs=selected_player_summary_table)
            selected_player.change(player_score_by_gameweek, inputs=selected_player, outputs=player_plot)
            selected_player.change(selected_player_rows, inputs=selected_player, outputs=selected_player_table)

        with gr.Tab("Score Breakdown"):
            gr.Markdown(
                "Translate SofaScore match statistics into their equivalent Sorare scoring impact. "
                "Understand which actions would add or remove Sorare points, and separate Decisive Score actions from All-Around Score actions.\n\n"
                "This is an analytical mapping layer from SofaScore stats to Sorare scoring logic. It is not the official SofaScore algorithm."
            )
            with gr.Row():
                breakdown_player = gr.Dropdown(
                    label="Player",
                    choices=breakdown_player_choices,
                    value=default_breakdown_player,
                    filterable=True,
                )
                breakdown_scope = gr.Dropdown(
                    label="Breakdown scope",
                    choices=["Filtered average", "All-time"],
                    value="Filtered average",
                )
                breakdown_season = gr.Dropdown(label="Season", choices=breakdown_season_choices, value="All")
                breakdown_tournament = gr.Dropdown(label="Tournament", choices=breakdown_tournament_choices, value="All")
            with gr.Row():
                breakdown_team = gr.Dropdown(label="Team", choices=breakdown_team_choices, value="All")
                breakdown_position = gr.Dropdown(label="Position", choices=breakdown_position_choices, value="All")
                breakdown_min_minutes = gr.Slider(label="Minimum minutes played", minimum=0, maximum=120, value=0, step=1)
                breakdown_starter = gr.Dropdown(
                    label="Starter / substitute",
                    choices=["All", "Starter", "Substitute", "Played from bench"],
                    value="All",
                )

            breakdown_kpis = gr.HTML(value=initial_breakdown_outputs[0], label="Player summary")
            breakdown_summary = gr.Dataframe(
                value=initial_breakdown_outputs[1],
                label="Estimated score contribution summary",
                interactive=False,
                wrap=True,
            )
            category_outputs = []
            table_index = 2
            for raw_label, score_label, _ in CATEGORY_TABLES:
                with gr.Tab(raw_label.replace(" Actions", "")):
                    raw_table = gr.Dataframe(
                        value=initial_breakdown_outputs[table_index],
                        label=raw_label,
                        interactive=False,
                        wrap=True,
                    )
                    score_table = gr.Dataframe(
                        value=initial_breakdown_outputs[table_index + 1],
                        label=score_label,
                        interactive=False,
                        wrap=True,
                    )
                    category_outputs.extend([raw_table, score_table])
                    table_index += 2

            match_inputs = [
                breakdown_player,
                breakdown_scope,
                breakdown_season,
                breakdown_tournament,
                breakdown_team,
                breakdown_position,
                breakdown_min_minutes,
                breakdown_starter,
            ]

            for control in match_inputs:
                control.change(
                    update_aggregate_score_breakdown,
                    inputs=match_inputs,
                    outputs=[breakdown_kpis, breakdown_summary, *category_outputs],
                )

        with gr.Tab("Teams"):
            team_search = gr.Textbox(label="Search teams", placeholder="Type a team")
            initial_team_table, initial_team_score, initial_team_scatter = update_team_view("")
            teams = gr.Dataframe(value=initial_team_table, label="Team profiles", interactive=False, wrap=True)
            with gr.Row():
                team_score = gr.Plot(value=initial_team_score, label="Score ranking")
                team_quality = gr.Plot(value=initial_team_scatter, label="Team attacking profile")
            team_search.change(update_team_view, inputs=team_search, outputs=[teams, team_score, team_quality])

        with gr.Tab("Match Stats"):
            with gr.Row():
                match_search = gr.Textbox(label="Search matches", placeholder="Home team, away team, or match key")
                status_filter = gr.Dropdown(label="Status", choices=status_choices, value="All")
                min_confidence = gr.Slider(label="Minimum match confidence", minimum=0, maximum=3, value=0, step=0.05)
            matches = gr.Dataframe(value=match_table("", "All", 0), label="SofaScore team-match stats", interactive=False, wrap=True)
            match_plot = gr.Plot(value=match_shots_chart("", "All", 0), label="Shot profile")
            for control in [match_search, status_filter, min_confidence]:
                control.change(match_table, inputs=[match_search, status_filter, min_confidence], outputs=matches)
                control.change(match_shots_chart, inputs=[match_search, status_filter, min_confidence], outputs=match_plot)

        with gr.Tab("Transfermarkt"):
            with gr.Row():
                tm_search = gr.Textbox(label="Search Transfermarkt context", placeholder="Club, player, or competition")
                tm_club_filter = gr.Dropdown(label="Club", choices=club_choices, value="All")
                tm_season_filter = gr.Dropdown(label="Season", choices=season_choices, value="All")
            tm_coverage = gr.Dataframe(
                value=transfermarkt_coverage_table("", "All", "All"),
                label="Transfermarkt coverage by club and season",
                interactive=False,
                wrap=True,
            )
            tm_missing = gr.Dataframe(
                value=transfermarkt_missing_dates("", "All", "All"),
                label="Club-dates with no Transfermarkt matchday squad",
                interactive=False,
                wrap=True,
            )
            tm_plot = gr.Plot(value=transfermarkt_coverage_chart("", "All", "All"), label="Transfermarkt coverage")
            for control in [tm_search, tm_club_filter, tm_season_filter]:
                control.change(
                    transfermarkt_coverage_table,
                    inputs=[tm_search, tm_club_filter, tm_season_filter],
                    outputs=tm_coverage,
                )
                control.change(
                    transfermarkt_missing_dates,
                    inputs=[tm_search, tm_club_filter, tm_season_filter],
                    outputs=tm_missing,
                )
                control.change(
                    transfermarkt_coverage_chart,
                    inputs=[tm_search, tm_club_filter, tm_season_filter],
                    outputs=tm_plot,
                )

        with gr.Tab("Data"):
            gr.Markdown(
                f"### Source Files\n"
                f"- `{MAIN_PATH.relative_to(PROJECT_ROOT)}`: {len(MAIN_DF):,} rows\n"
                f"- `{SCORE_BREAKDOWN_PATH.relative_to(PROJECT_ROOT)}`: {len(SCORE_BREAKDOWN_DF):,} rows\n"
                f"- `{TEAM_PATH.relative_to(PROJECT_ROOT)}`: {len(TEAM_DF):,} rows\n"
                f"- `{MATCH_STATS_PATH.relative_to(PROJECT_ROOT)}`: {len(MATCH_DF):,} rows\n\n"
                "This dashboard is modeled after the SORARE V3 Gradio dashboard and adapted for the SORARE V4 datasets."
            )

    return app


if __name__ == "__main__":
    build_dashboard().launch()
