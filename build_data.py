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

import numpy as np

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
    # Ranked and displayed by composite_score_reliable (minutes-shrunk toward
    # the pool average -- see scoring.py's _apply_reliability_shrinkage),
    # not the raw composite_score: a thin-sample standout (a squad player's
    # one hot cameo) shouldn't outrank a full season of sustained form just
    # because the raw per-90 rate happens to match. The raw score is kept
    # alongside (score_raw) for transparency, not hidden.
    p = pd.read_csv(data_dir / "player/player_quality.csv")
    latest = p[(p["season"] == LATEST_SEASON) & (p["minutes"] >= 450)].copy()
    players_out = {}
    for sp in SUBPOS_ORDER:
        sub = latest[latest["sub_position"] == sp].sort_values("composite_score_reliable", ascending=False).head(8)
        players_out[sp] = [
            {
                "player": r["player"], "squad": r["squad"],
                "age": int(r["age"]) if pd.notna(r["age"]) else None,
                "minutes": int(r["minutes"]),
                "score": round(float(r["composite_score_reliable"]), 3),
                "score_raw": round(float(r["composite_score"]), 3),
            }
            for _, r in sub.iterrows()
        ]

    # ---- Players: full filterable roster ----
    all_sorted = latest.sort_values("composite_score_reliable", ascending=False)
    players_all = [
        {
            "player": r["player"], "squad": r["squad"], "sub_position": r["sub_position"],
            "age": int(r["age"]) if pd.notna(r["age"]) else None,
            "minutes": int(r["minutes"]),
            "score": round(float(r["composite_score_reliable"]), 3),
            "score_raw": round(float(r["composite_score"]), 3),
        }
        for _, r in all_sorted.iterrows()
    ]
    clubs_list = sorted(latest["squad"].unique().tolist())

    # ---- Clubs: every season transition, not just the latest ----
    t = pd.read_csv(data_dir / "transition/core_quality_delta.csv")
    transition_seasons = sorted(t["season_to"].unique())
    club_transitions = {}
    for season_to in transition_seasons:
        rows = t[t["season_to"] == season_to].sort_values("core_quality_delta", ascending=False, na_position="last")
        club_transitions[season_to] = [
            {
                "club": r["club"],
                "from": clean(round(float(r["core_quality_from"]), 3)) if pd.notna(r["core_quality_from"]) else None,
                "to": round(float(r["core_quality_to"]), 3),
                "delta": clean(round(float(r["core_quality_delta"]), 3)) if pd.notna(r["core_quality_delta"]) else None,
                "added": clean(round(float(r["quality_added"]), 3)) if pd.notna(r["quality_added"]) else None,
                "lost": clean(round(float(r["quality_lost"]), 3)) if pd.notna(r["quality_lost"]) else None,
            }
            for _, r in rows.iterrows()
        ]
    clubs_out = club_transitions[LATEST_SEASON]  # kept for back-compat / default view

    # ---- Who actually moved: the players behind quality_added / quality_lost ----
    # Mirrors transition.py's _added_lost exactly (a player is "added" if he's in
    # this season's core squad and wasn't in last season's, and vice versa), so
    # these lists sum back to the headline Added/Lost figures rather than being a
    # loosely-related roster diff. Verified: Manchester Utd 2025-26 added sums to
    # 0.123 against the transition layer's own 0.123.
    core = pd.read_csv(data_dir / "club/core_players.csv")

    def _fmt_movers(frame):
        return [
            {
                "player": r["player"],
                "sub_position": clean(r.get("sub_position")),
                "minutes": int(r["minutes"]),
                # 2 of 2,793 core rows have no composite (missing every stat in
                # every category for that season). pandas' .sum() skips them, so
                # the headline Added/Lost is unaffected -- surface them as null
                # rather than dropping the player from the list entirely.
                "contribution": None if pd.isna(r["quality_contribution"]) else round(float(r["quality_contribution"]), 3),
                "score": None if pd.isna(r["composite_score_reliable"]) else round(float(r["composite_score_reliable"]), 2),
            }
            for _, r in frame.sort_values("quality_contribution", ascending=False, na_position="last").iterrows()
        ]

    squad_changes = {}
    for season_to in transition_seasons:
        rows = t[t["season_to"] == season_to]
        season_from_vals = rows["season_from"].dropna()
        if season_from_vals.empty:
            continue
        season_from = season_from_vals.iloc[0]
        cur_all, prev_all = core[core["season"] == season_to], core[core["season"] == season_from]
        per_club = {}
        for club in rows["club"].unique():
            cur = cur_all[cur_all["squad"] == club]
            prev = prev_all[prev_all["squad"] == club]
            # No prior-season core (promoted club) -> nothing meaningful to diff.
            if prev.empty:
                continue
            added = cur[~cur["player_id"].isin(prev["player_id"])]
            lost = prev[~prev["player_id"].isin(cur["player_id"])]
            per_club[club] = {
                "added": _fmt_movers(added),
                "lost": _fmt_movers(lost),
                "kept": int(len(cur) - len(added)),
            }
        squad_changes[season_to] = per_club

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
    # Uses the enriched file (transfer_window.csv + cross-league projections
    # for signings with no Premier League history -- see cross_league.py).
    # Falls back to the plain file if projections haven't been generated, so
    # this never hard-fails on a fresh checkout.
    enriched_path = data_dir / "exploratory/transfer_window_enriched.csv"
    if enriched_path.exists():
        tw = pd.read_csv(enriched_path)
        from pl_predictive_model.cross_league import summarize_with_projections  # noqa: E402
        summary = summarize_with_projections(tw).rename(columns={"rating_with_projections": "rating"})
    else:
        tw = pd.read_csv(data_dir / "exploratory/transfer_window.csv")
        tw["rating_source"] = np.where(tw["rated"], "premier_league", "unrated")
        tw["effective_rating"] = tw["composite_score_reliable"]
        tw["rating_pl_data_only"] = np.nan
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
                "rating_source": clean(x.get("rating_source")) or "unrated",
                # `score` is what the club rating actually used: a real PL
                # composite where we have one, else the cross-league estimate.
                "score": None if pd.isna(x.get("effective_rating")) else round(float(x["effective_rating"]), 3),
                "score_raw": None if pd.isna(x["composite_score"]) else round(float(x["composite_score"]), 3),
                "from_league": clean(x.get("projected_from_league")),
                "from_minutes": None if pd.isna(x.get("projected_from_minutes")) else int(x["projected_from_minutes"]),
                "sub_position": clean(x.get("sub_position")),
            })
        return rows

    transfer_summary = []
    for _, r in summary.iterrows():
        club = r["club"]
        club_transfers = tw[tw["club"] == club]
        inbound = club_transfers[club_transfers["direction"] == "in"].sort_values("effective_rating", ascending=False, na_position="last")
        outbound = club_transfers[club_transfers["direction"] == "out"].sort_values("effective_rating", ascending=True, na_position="last")
        transfer_summary.append({
            "club": club,
            "rating": round(float(r["rating"]), 3),
            "rating_pl_only": None if pd.isna(r.get("rating_pl_data_only")) else round(float(r["rating_pl_data_only"]), 3),
            "in": fmt_side(inbound), "out": fmt_side(outbound),
        })

    return {
        "players": players_out,
        "players_all": players_all,
        "clubs_list": clubs_list,
        "clubs": clubs_out,
        "club_transitions": club_transitions,
        "squad_changes": squad_changes,
        "transition_seasons": transition_seasons,
        "club_history": {"seasons": seasons, "rows": history_rows},
        "transfers": transfer_summary,
    }


if __name__ == "__main__":
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    result = build(source)
    text = json.dumps(result, allow_nan=False)
    OUT_PATH.write_text(text)
    print(f"Wrote {OUT_PATH} ({len(text):,} bytes)")
