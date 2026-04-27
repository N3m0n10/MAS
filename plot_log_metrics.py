#!/usr/bin/env python3
"""
plot_log_metrics.py
===================
Builds runtime graphs from JaCaMo/Jason log output.

Metrics plotted:
1) % of theoretical maximum contract value over time
2) Strategy advantage (cumulative wins per strategy)
3) Average awarded contracts per initiator over time

Usage:
    python3 plot_log_metrics.py --log log/mas-0.log
"""

from __future__ import annotations

import argparse
import glob
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


SERVICE_VALUE = 200.0


@dataclass
class RunConfig:
    n: int
    m: int
    i: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate runtime metric graphs from JaCaMo logs")
    parser.add_argument("--log", help="Path to runtime log file")
    parser.add_argument("--jcm", default="cnp_project.jcm", help="Path to .jcm config file")
    parser.add_argument("--out", default="log/runtime_metrics.png", help="Output PNG path")
    return parser.parse_args()


def find_latest_log() -> str | None:
    patterns = [
        "log/mas-*.log",
        "log/cnp_run_*.log",
        "*.log",
    ]
    candidates: list[str] = []
    for p in patterns:
        candidates.extend(glob.glob(p))

    candidates = [c for c in candidates if os.path.isfile(c) and os.path.getsize(c) > 0]
    if not candidates:
        return None

    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def parse_config_from_jcm(jcm_path: str) -> RunConfig:
    text = Path(jcm_path).read_text(encoding="utf-8", errors="ignore")
    m_n = re.search(r"Configuration:\s*n=(\d+)\s+initiators", text)
    m_m = re.search(r"m=(\d+)\s+participants", text)
    m_i = re.search(r"i=(\d+)\s+contracts/initiator", text)

    if m_n and m_m and m_i:
        return RunConfig(int(m_n.group(1)), int(m_m.group(1)), int(m_i.group(1)))

    # Fallback from agent declarations if header comment is missing.
    n = len(re.findall(r"^\s*agent\s+initiator\d+\s*:", text, flags=re.MULTILINE))
    m = len(re.findall(r"^\s*agent\s+participant\d+\s*:", text, flags=re.MULTILINE))

    # Use first initiator's num_contracts as i fallback.
    m_i2 = re.search(r"num_contracts\((\d+)\)", text)
    i = int(m_i2.group(1)) if m_i2 else 10

    if n <= 0 or m <= 0:
        raise RuntimeError("Could not infer n/m from .jcm file")

    return RunConfig(n, m, i)


def maybe_parse_config_from_log(text: str) -> RunConfig | None:
    m = re.search(r"\[MetricsBoard\] Initialized:\s*n=(\d+),\s*m=(\d+),\s*i=(\d+)", text)
    if not m:
        return None
    return RunConfig(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def build_series(log_text: str, cfg: RunConfig) -> dict:
    # Example line:
    # [participant8] [P-S2 8] WON contract #5010 value=100
    won_pat = re.compile(
        r"\[participant\d+\]\s+\[P-S([123])\s+\d+\]\s+WON\s+contract\s+#(\d+)\s+value=([-+]?\d+(?:\.\d+)?)",
        flags=re.IGNORECASE,
    )

    proposal_pat = re.compile(
        r"\[participant\d+\]\s+\[P-S([123])\s+\d+\]\s+CFP\s+#(\d+)\s+from\s+initiator\d+\s+proposing(?:\s+fixed)?\s+([-+]?\d+(?:\.\d+)?)",
        flags=re.IGNORECASE,
    )

    wins_s1 = 0
    wins_s2 = 0
    wins_s3 = 0
    cum_value = 0.0
    event_idx = 0

    seen_awarded_contracts: set[int] = set()

    xs: list[int] = []
    pct_series: list[float] = []
    avg_contracts_series: list[float] = []
    s1_series: list[int] = []
    s2_series: list[int] = []
    s3_series: list[int] = []

    # With current policy, each contract may accept up to K=10 offers.
    # For m<10, at most m offers can be accepted.
    k_accept = min(10, cfg.m)
    theo_max = cfg.n * cfg.i * k_accept * SERVICE_VALUE

    for line in log_text.splitlines():
        m = won_pat.search(line)
        if not m:
            continue

        strat = int(m.group(1))
        contract_id = int(m.group(2))
        value = float(m.group(3))

        event_idx += 1
        cum_value += value

        if strat == 1:
            wins_s1 += 1
        elif strat == 2:
            wins_s2 += 1
        else:
            wins_s3 += 1

        seen_awarded_contracts.add(contract_id)

        pct = (cum_value / theo_max) * 100.0 if theo_max > 0 else 0.0
        avg_contracts = (len(seen_awarded_contracts) / cfg.n) if cfg.n > 0 else 0.0

        xs.append(event_idx)
        pct_series.append(pct)
        avg_contracts_series.append(avg_contracts)
        s1_series.append(wins_s1)
        s2_series.append(wins_s2)
        s3_series.append(wins_s3)

    if event_idx > 0:
        return {
            "mode": "awards",
            "xs": xs,
            "pct": pct_series,
            "avg_contracts": avg_contracts_series,
            "s1": s1_series,
            "s2": s2_series,
            "s3": s3_series,
            "wins": {"S1": wins_s1, "S2": wins_s2, "S3": wins_s3},
            "events": event_idx,
            "theo_max": theo_max,
        }

    # This works even if WON lines are missing in shorter runs.
    contract_bids: dict[int, list[tuple[float, int]]] = {}

    xs = []
    pct_series = []
    avg_contracts_series = []
    s1_series = []
    s2_series = []
    s3_series = []

    event_idx = 0
    for line in log_text.splitlines():
        m = proposal_pat.search(line)
        if not m:
            continue

        strat = int(m.group(1))
        contract_id = int(m.group(2))
        value = float(m.group(3))

        event_idx += 1
        contract_bids.setdefault(contract_id, []).append((value, strat))

        total_selected_value = 0.0
        selected_s1 = 0
        selected_s2 = 0
        selected_s3 = 0
        selected_contracts = 0

        for bids in contract_bids.values():
            if not bids:
                continue
            selected_contracts += 1
            chosen = sorted(bids, key=lambda b: b[0])[: min(10, len(bids))]
            for v, s in chosen:
                total_selected_value += v
                if s == 1:
                    selected_s1 += 1
                elif s == 2:
                    selected_s2 += 1
                else:
                    selected_s3 += 1

        pct = (total_selected_value / theo_max) * 100.0 if theo_max > 0 else 0.0
        avg_contracts = (selected_contracts / cfg.n) if cfg.n > 0 else 0.0

        xs.append(event_idx)
        pct_series.append(pct)
        avg_contracts_series.append(avg_contracts)
        s1_series.append(selected_s1)
        s2_series.append(selected_s2)
        s3_series.append(selected_s3)

    return {
        "mode": "proposals",
        "xs": xs,
        "pct": pct_series,
        "avg_contracts": avg_contracts_series,
        "s1": s1_series,
        "s2": s2_series,
        "s3": s3_series,
        "wins": {
            "S1": s1_series[-1] if s1_series else 0,
            "S2": s2_series[-1] if s2_series else 0,
            "S3": s3_series[-1] if s3_series else 0,
        },
        "events": event_idx,
        "theo_max": theo_max,
    }


def plot(series: dict, cfg: RunConfig, out_path: str) -> None:
    if series["events"] == 0:
        raise RuntimeError(
            "No parseable proposal or award lines found in log. "
            "Cannot build time-series metrics."
        )

    xs = series["xs"]

    fig, axes = plt.subplots(3, 1, figsize=(12, 12), sharex=True)
    mode_label = "awards" if series.get("mode") == "awards" else "proposal-derived"
    closed = series.get("closed_contracts", 0)
    expected = series.get("expected_contracts", cfg.n * cfg.i)
    fig.suptitle(
        (
            f"CNP Runtime Metrics (n={cfg.n}, m={cfg.m}, i={cfg.i}, "
            f"mode={mode_label}, closed={closed}/{expected})"
        ),
        fontsize=14,
        fontweight="bold",
    )

    # 1) % of theoretical max value over time
    axes[0].plot(xs, series["pct"], color="#1f77b4", linewidth=2)
    axes[0].set_ylabel("% Theoretical Value")
    axes[0].set_title("Efficiency Over Time")
    axes[0].grid(True, linestyle="--", alpha=0.4)

    # 2) Strategy advantage over time (cumulative wins)
    axes[1].plot(xs, series["s1"], label="S1 Random", color="#4c78a8", linewidth=2)
    axes[1].plot(xs, series["s2"], label="S2 Adaptive", color="#f58518", linewidth=2)
    axes[1].plot(xs, series["s3"], label="S3 Fixed", color="#54a24b", linewidth=2)
    axes[1].set_ylabel("Cumulative Wins")
    axes[1].set_title("Strategy Advantage Over Time")
    axes[1].legend(loc="upper left")
    axes[1].grid(True, linestyle="--", alpha=0.4)

    final_wins = series["wins"]
    leader = max(final_wins, key=final_wins.get)
    axes[1].text(
        0.99,
        0.03,
        f"Leader: {leader} ({final_wins[leader]} wins)",
        transform=axes[1].transAxes,
        ha="right",
        va="bottom",
        fontsize=10,
        bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "#cccccc"},
    )

    # 3) Avg awarded contracts per initiator over time
    axes[2].plot(xs, series["avg_contracts"], color="#2ca02c", linewidth=2)
    axes[2].set_ylabel("Avg Contracts/Initiator")
    axes[2].set_xlabel("Award Event Index")
    axes[2].set_title("Average Awarded Contracts per Initiator Over Time")
    axes[2].grid(True, linestyle="--", alpha=0.4)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0.02, 1, 0.98])
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> None:
    args = parse_args()

    log_path = args.log or find_latest_log()
    if not log_path:
        raise RuntimeError("No non-empty log file found. Run the simulation first.")

    log_text = Path(log_path).read_text(encoding="utf-8", errors="ignore")

    cfg = maybe_parse_config_from_log(log_text)
    if cfg is None:
        cfg = parse_config_from_jcm(args.jcm)

    series = build_series(log_text, cfg)
    series["expected_contracts"] = cfg.n * cfg.i
    series["closed_contracts"] = len(re.findall(r"closed with", log_text))
    plot(series, cfg, args.out)

    print(f"Log source: {log_path}")
    print(f"Output graph: {args.out}")
    print(f"Award events parsed: {series['events']}")
    print(f"Final strategy wins: {series['wins']}")
    print(
        "Closed contracts: "
        f"{series['closed_contracts']}/{series['expected_contracts']}"
    )
    if series["closed_contracts"] < series["expected_contracts"]:
        print(
            "WARNING: Log appears incomplete. "
            "Interpret metrics as partial-run values."
        )


if __name__ == "__main__":
    main()
