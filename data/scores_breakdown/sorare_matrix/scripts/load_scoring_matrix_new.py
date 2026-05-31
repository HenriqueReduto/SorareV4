from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
MATRIX_PATH = BASE_DIR / "data" / "scoring_matrix_new.csv"
RULES_PATH = BASE_DIR / "data" / "player_score_rules.txt"


def main() -> None:
    matrix = pd.read_csv(MATRIX_PATH)

    print(matrix.head())
    print()
    print(RULES_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
