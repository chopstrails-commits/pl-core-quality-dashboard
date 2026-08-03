"""Regenerate data.json from the CQ_v1 pipeline's output.

Reads from the PL Predictive Model project's data/ directory (the source of
truth -- this repo does not duplicate the pipeline, only its published
output). Run this, then build_site.py, whenever the underlying pipeline is
re-run (new season data, a re-scored player pool, a fresh transfer pull).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

DEFAULT_SOURCE = Path("/Users/bo/Desktop/Bo/PL Predictive Model")
OUT_PATH = Path(__file__).parent / "data.json"

LATEST_SEASON = "2025-26"
SUBPOS_ORDER = ["GK", "CB", "FB", "DM", "CM", "AM", "W", "FW"]


def clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def build(source: Path) -> dict:
    data_dir = source / "data"
    sys.path.insert(0, str(source / "src"))
    from pl_predictive_model.transfer_window import summarize_by_club  # noqa: E402

    # ---- Players: top-8 leaderboard per sub-position ----
    p = pd.read_csv(data_dir / "player/player_quality.csv")
    latest = p[(p["season"] == LATEST_SEASON) & (p["minutes"] >= 450)].copy()
    players_out = {}
    for sp in SUBPOS_ORDER:
        sub = latest[latest["sub_position"] == sp].sort_values("composite_score", ascending=False).head(8)
        players_out[sp] = [
            {
                "player": r["player"], "squad": r["squad"],
                "age": int(r["age"]) if pd.notna(r["age"]) else None,
                "minutes": int(r["minutes"]), "score": round(float(r["composite_score"]), 3),
            }
            for _, r in sub.iterrows()
        ]

    # ---- Players: full filterable roster ----
    all_sorted = latest.sort_values("composite_score", ascending=False)
    players_all = [
        {
            "player": r["player"], "squad": r["squad"], "sub_position": r["sub_position"],
            "age": int(r["age"]) if pd.notna(r["age"]) else None,
            "minutes": int(r["minutes"]), "score": round(float(r["composite_score"]), 3),
        }
        for _, r in all_sorted.iterrows()
    ]
    clubs_list = sorted(latest["squad"].unique().tolist())

    # ---- Clubs: latest transition ----
    t = pd.read_csv(data_dir / "transition/core_quality_delta.csv")
    latest_t = t[t["season_to"] == LATEST_SEASON].sort_values("core_quality_delta", ascending=False, na_position="last")
    clubs_out = [
        {
            "club": r["club"],
            "from": clean(round(float(r["core_quality_from"]), 3)) if pd.notna(r["core_quality_from"]) else None,
            "to": round(float(r["core_quality_to"]), 3),
            "delta": clean(round(float(r["core_quality_delta"]), 3)) if pd.notna(r["core_quality_delta"]) else None,
            "added": clean(round(float(r["quality_added"]), 3)) if pd.notna(r["quality_added"]) else None,
            "lost": clean(round(float(r["quality_lost"]), 3)) if pd.notna(r["quality_lost"]) else None,
        }
        for _, r in latest_t.iterrows()
    ]

    # ---- Clubs: full season history ----
    c = pd.read_csv(data_dir / "club/club_core_quality.csv")
    seasons = sorted(c["season"].unique())
    pivot = c.pivot(index="club", columns="season", values="core_quality")

    def sort_key(club):
        row = pivot.loc[club]
        for s in reversed(seasons):
            if pd.notna(row[s]):
                return -row[s]
        return -row.mean() if pd.notna(row.mean()) else 999

    clubs_sorted = sorted(pivot.index.tolist(), key=sort_key)
    history_rows = [
        {"club": club, "values": [None if pd.isna(pivot.loc[club, s]) else round(float(pivot.loc[club, s]), 3) for s in seasons]}
        for club in clubs_sorted
    ]

    # ---- Transfer window ----
    tw = pd.read_csv(data_dir / "exploratory/transfer_window.csv")
    summary = summarize_by_club(tw).sort_values("rating", ascending=False)

    def fmt_side(df):
        rows = []
        for _, x in df.iterrows():
            fee = clean(x.get("fee"))
            rows.append({
                "player": x["player"], "counterparty": clean(x.get("counterparty")),
                "fee": round(float(fee)) if fee is not None else None,
                "on_loan": bool(x["on_loan"]) if pd.notna(x.get("on_loan")) else False,
                "rated": bool(x["rated"]),
                "score": None if pd.isna(x["composite_score"]) else round(float(x["composite_score"]), 3),
                "sub_position": clean(x.get("sub_position")),
            })
        return rows

    transfer_summary = []
    for _, r in summary.iterrows():
        club = r["club"]
        club_transfers = tw[tw["club"] == club]
        inbound = club_transfers[club_transfers["direction"] == "in"].sort_values("composite_score", ascending=False, na_position="last")
        outbound = club_transfers[club_transfers["direction"] == "out"].sort_values("composite_score", ascending=True, na_position="last")
        transfer_summary.append({
            "club": club, "rating": round(float(r["rating"]), 3),
            "in": fmt_side(inbound), "out": fmt_side(outbound),
        })

    return {
        "players": players_out,
        "players_all": players_all,
        "clubs_list": clubs_list,
        "clubs": clubs_out,
        "club_history": {"seasons": seasons, "rows": history_rows},
        "transfers": transfer_summary,
    }


if __name__ == "__main__":
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    result = build(source)
    text = json.dumps(result, allow_nan=False)
    OUT_PATH.write_text(text)
    print(f"Wrote {OUT_PATH} ({len(text):,} bytes)")
