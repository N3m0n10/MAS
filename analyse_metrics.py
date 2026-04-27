#!/usr/bin/env python3
"""
analyse_metrics.py
==================
Reads CNP report files (cnp_report_*.txt) and produces a
comparative analysis table + charts across (n, m, i) configurations.

Supports:
- Multi-run aggregation with confidence intervals
- CSV/JSON export for programmatic consumption
- Fairness index computation (Gini/stddev)
- Latency percentiles (p50, p95, p99) when available
- Convergence analysis for Strategy 2 (adaptive)
- Statistical significance testing between strategies

Requires: matplotlib, pandas, numpy
    pip install matplotlib pandas numpy

Usage:
    python analyse_metrics.py                          # reads all cnp_report_*.txt
    python analyse_metrics.py --dir ./results          # reads from a specific dir
    python analyse_metrics.py --runs 5 --aggregate     # aggregate 5 runs per config
"""

import os, re, glob, argparse, json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path
from collections import defaultdict

# ── Report parser ────────────────────────────────────────────
PATTERNS = {
    "n":             r"Configuration: n=(\d+) initiators",
    "m":             r"m=(\d+) participants",
    "i":             r"i=(\d+) contracts/initiator",
    "elapsed_s":     r"Elapsed time\s*:\s*([\d.]+)\s*s",
    "theo_max":      r"Theoretical max contracts\s*:\s*(\d+)",
    "theo_val":      r"Theoretical max value\s*:\s*([\d.]+)",
    "awarded":       r"Contracts AWARDED\s*:\s*(\d+)",
    "failed":        r"Contracts FAILED\s*:\s*(\d+)",
    "total_value":   r"Total value\s*:\s*([\d.]+)",
    "pct":           r"% of theoretical\s*:\s*([\d.]+)",
    "s1_wins":       r"S1 \(Random\)\s+wins=(\d+)",
    "s2_wins":       r"S2 \(Adaptive\)\s+wins=(\d+)",
    "s3_wins":       r"S3 \(Fixed\)\s+wins=(\d+)",
    "s1_total":      r"S1 \(Random\)\s+wins=\d+\s+total=([\d.]+)",
    "s2_total":      r"S2 \(Adaptive\)\s+wins=\d+\s+total=([\d.]+)",
    "s3_total":      r"S3 \(Fixed\)\s+wins=\d+\s+total=([\d.]+)",
    "s1_avg":        r"S1 \(Random\)\s+wins=\d+\s+total=[\d.]+\s+avg=([\d.]+)",
    "s2_avg":        r"S2 \(Adaptive\)\s+wins=\d+\s+total=[\d.]+\s+avg=([\d.]+)",
    "s3_avg":        r"S3 \(Fixed\)\s+wins=\d+\s+total=[\d.]+\s+avg=([\d.]+)",
    "avg_contracts": r"Avg contracts/initiator:\s*([\d.]+)",
    "thresh_rej_n":  r"Threshold Rejections:\s*(\d+)\s*/\s*(\d+)\s+proposals",
    "thresh_rej_pct":r"Threshold Rejections:\s*\d+\s*/\s*\d+\s+proposals\s+\(([\d.]+)",
    "avg_latency":   r"Avg award latency\s*:\s*([\d.]+)\s+ms",
    "proposal_rate": r"Proposal arrival\s*:\s*([\d.]+)\s+proposals/s",
    "s1_avg_win":    r"S1.*avg_win=([\d.]+)",
    "s2_avg_win":    r"S2.*avg_win=([\d.]+)",
    "s3_avg_win":    r"S3.*avg_win=([\d.]+)",
    # Per-initiator: e.g., "Initiator 1: 3 contracts, value=450.0, avg=150.0"
    "init_avg_variance": r"Avg contracts/initiator:\s*([\d.]+)",  # same as avg_contracts
}

# Latency percentiles (p50, p95, p99) are computed from stored per-award times
# when MetricsBoard is enhanced with individual award time tracking
PER_AWARD_TIMES_PATTERNS = []  # Placeholder for future per-award extraction

def parse_report(filepath: str) -> dict | None:
    with open(filepath) as f:
        text = f.read()
    row = {"file": os.path.basename(filepath), "path": filepath}

    # Extract config from filename if possible
    fname = os.path.basename(filepath)
    config_match = re.search(r"n(\d+)_m(\d+)_i(\d+)", fname)
    if config_match:
        row["config_n"] = int(config_match.group(1))
        row["config_m"] = int(config_match.group(2))
        row["config_i"] = int(config_match.group(3))

    for key, pat in PATTERNS.items():
        m = re.search(pat, text)
        if m:
            try:
                row[key] = float(m.group(1))
            except:
                row[key] = m.group(1)
        else:
            row[key] = None

    # Parse per-initiator data
    row["per_initiator"] = {}
    for m in re.finditer(r"Initiator (\d+):\s*(\d+)\s*contracts,\s*value=([\d.]+),\s*avg=([\d.]+)", text):
        init_id = int(m.group(1))
        contracts = int(m.group(2))
        value = float(m.group(3))
        avg = float(m.group(4))
        row["per_initiator"][init_id] = {"contracts": contracts, "value": value, "avg": avg}

    return row

def load_all_reports(directory: str) -> pd.DataFrame:
    files = glob.glob(os.path.join(directory, "cnp_report_*.txt"))
    if not files:
        print(f"No cnp_report_*.txt files found in '{directory}'.")
        return pd.DataFrame()
    rows = [parse_report(f) for f in files]
    df = pd.DataFrame(rows)

    # Cast numeric cols
    num_cols = ["n","m","i","elapsed_s","theo_max","theo_val","awarded","failed",
               "total_value","pct","s1_wins","s2_wins","s3_wins",
               "s1_avg","s2_avg","s3_avg","s1_avg_win","s2_avg_win","s3_avg_win",
               "avg_contracts","avg_latency","proposal_rate","thresh_rej_pct"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df.sort_values(["n","m","i"]).reset_index(drop=True)

# ── Fairness metrics ─────────────────────────────────────────
def compute_fairness(df: pd.DataFrame) -> pd.DataFrame:
    """Compute fairness index from per-initiator data using Gini coefficient and stddev."""
    fairness_rows = []
    for _, row in df.iterrows():
        n = int(row.get("n", 0))
        if n == 0 or "per_initiator" not in row or not row["per_initiator"]:
            fairness_rows.append({"gini": None, "stddev": None, "cv": None})
            continue

        counts = [row["per_initiator"][i]["contracts"]
                  for i in sorted(row["per_initiator"].keys())]

        # Gini coefficient
        sorted_counts = sorted(counts)
        n_count = len(sorted_counts)
        cumsum = np.cumsum(sorted_counts)
        gini = (2 * np.sum((np.arange(1, n_count + 1)) * sorted_counts)) / (n_count * cumsum[-1]) - (n_count + 1) / n_count if cumsum[-1] > 0 else 0

        # Stddev and coefficient of variation
        std = np.std(counts) if len(counts) > 1 else 0
        mean = np.mean(counts)
        cv = std / mean if mean > 0 else 0

        fairness_rows.append({"gini": gini, "stddev": std, "cv": cv})

    fairness_df = pd.DataFrame(fairness_rows)
    return pd.concat([df.reset_index(drop=True), fairness_df], axis=1)

# ── Multi-run aggregation ─────────────────────────────────────
def aggregate_runs(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate multiple runs of same (n,m,i) config. Adds mean, std, confidence intervals."""
    grouped = df.groupby(["n","m","i"])

    agg = grouped.agg({
        "awarded": ["mean","std","count"],
        "failed": ["mean","std"],
        "total_value": ["mean","std"],
        "pct": ["mean","std"],
        "s1_wins": ["mean","std"],
        "s2_wins": ["mean","std"],
        "s3_wins": ["mean","std"],
        "s1_avg": ["mean","std"],
        "s2_avg": ["mean","std"],
        "s3_avg": ["mean","std"],
        "avg_contracts": ["mean","std"],
        "avg_latency": ["mean","std"],
        "proposal_rate": ["mean","std"],
        "thresh_rej_pct": ["mean","std"],
    }).reset_index()

    # Flatten column names
    agg.columns = ['_'.join(col).strip('_') for col in agg.columns.values]
    return agg

def compute_confidence_interval(values, confidence=0.95):
    """Compute mean ± CI for a series of values."""
    if len(values) < 2:
        return values.mean() if len(values) == 1 else None, None, None
    mean = values.mean()
    std = values.std()
    ci = 1.96 * std / np.sqrt(len(values))  # 95% CI
    return mean, std, ci

# ── CSV/JSON export ───────────────────────────────────────────
def export_csv(df: pd.DataFrame, out_dir: str, prefix: str = "cnp_analysis"):
    """Export aggregated data to CSV for downstream analysis."""
    csv_path = os.path.join(out_dir, f"{prefix}_summary.csv")
    df.to_csv(csv_path, index=False)
    print(f"CSV export: {csv_path}")

def export_json(df: pd.DataFrame, out_dir: str, prefix: str = "cnp_analysis"):
    """Export data to JSON for programmatic consumption."""
    records = df.to_dict(orient="records")
    json_path = os.path.join(out_dir, f"{prefix}_summary.json")
    with open(json_path, "w") as f:
        json.dump(records, f, indent=2, default=str)
    print(f"JSON export: {json_path}")

# ── Statistical significance ──────────────────────────────────
def strategy_significance(df: pd.DataFrame) -> dict:
    """
    Test if strategy win rates differ significantly using Chi-square test.
    Returns dict with chi2 statistic and p-value per config.
    """
    try:
        from scipy import stats
        has_scipy = True
    except ImportError:
        has_scipy = False

    results = []
    for _, row in df.iterrows():
        n = int(row.get("n", 0))
        m = int(row.get("m", 0))
        i = int(row.get("i", 0))
        s1 = int(row.get("s1_wins", 0) or 0)
        s2 = int(row.get("s2_wins", 0) or 0)
        s3 = int(row.get("s3_wins", 0) or 0)
        awarded = int(row.get("awarded", 0) or 0)

        # Count "not won" for each strategy (proportional to their agent count)
        s1_agents = max(1, int(np.ceil(m / 3)))
        s2_agents = max(1, int(np.ceil(2 * m / 3) - np.ceil(m / 3)))
        s3_agents = max(1, m - s2_agents - s1_agents)

        # Build contingency table: [wins, not_wins] per strategy
        s1_not = s1_agents * i * n - s1
        s2_not = s2_agents * i * n - s2
        s3_not = s3_agents * i * n - s3

        result = {"n": n, "m": m, "i": i, "s1_wins": s1, "s2_wins": s2, "s3_wins": s3}
        result["s1_agents"] = s1_agents
        result["s2_agents"] = s2_agents
        result["s3_agents"] = s3_agents

        if has_scipy and awarded > 0:
            contingency = [[s1, s1_not], [s2, s2_not], [s3, s3_not]]
            try:
                chi2, p, dof, expected = stats.chi2_contingency(contingency)
                result["chi2"] = round(chi2, 4)
                result["p_value"] = round(p, 6)
                result["significant"] = p < 0.05
            except Exception as e:
                result["chi2"] = None
                result["p_value"] = None
                result["significant"] = None
                result["error"] = str(e)
        else:
            result["chi2"] = None
            result["p_value"] = None
            result["significant"] = None
            result["note"] = "scipy not available or insufficient data"

        results.append(result)

    return results

# ── Convergence analysis for S2 ────────────────────────────────
def convergence_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """
    Analyze if Strategy 2 (Adaptive) improves over time.
    Requires per-initiator contract sequence data.
    This uses the avg_contracts and s2_wins to estimate convergence.
    """
    results = []
    for _, row in df.iterrows():
        n = int(row.get("n", 0))
        i = int(row.get("i", 0))
        s2_wins = int(row.get("s2_wins", 0) or 0)
        s2_avg = row.get("s2_avg", 0) or 0

        # Theoretical S2 participation: ceil(2m/3) - ceil(m/3) agents
        # Each has i contracts per initiator
        # We can't know early vs late without per-award timestamps,
        # but we can look at relative S2 performance across configs

        # Compute an "adaptive efficiency" metric:
        # ratio of S2 wins to S2 agent count, normalized by total contracts
        m = int(row.get("m", 0))
        if m > 0:
            s2_agents = max(1, int(np.ceil(2 * m / 3) - np.ceil(m / 3)))
            theoretical_max_s2 = n * i * s2_agents
            efficiency = s2_wins / theoretical_max_s2 if theoretical_max_s2 > 0 else 0
        else:
            efficiency = 0

        results.append({
            "n": n, "m": m, "i": i,
            "s2_wins": s2_wins,
            "s2_efficiency": round(efficiency, 4),
            "s2_avg_value": s2_avg,
        })

    return pd.DataFrame(results)

# ── Console report ───────────────────────────────────────────
def print_table(df: pd.DataFrame):
    print("\n" + "="*120)
    print("CONTRACT NET PROTOCOL – COMPARATIVE ANALYSIS")
    print("="*120)
    cols = ["n","m","i","awarded","failed","total_value","pct",
            "s1_wins","s2_wins","s3_wins","s1_avg","s2_avg","s3_avg","avg_contracts",
            "avg_latency","proposal_rate","thresh_rej_pct"]
    available = [c for c in cols if c in df.columns]
    print(df[available].to_string(index=False, float_format="{:.2f}".format))
    print("="*120)

    print("\nPer-strategy avg winning price:")
    for _, row in df.iterrows():
        s1_avg = row.get('s1_avg_win', 0) or 0
        s2_avg = row.get('s2_avg_win', 0) or 0
        s3_avg = row.get('s3_avg_win', 0) or 0
        print(f"  n={int(row['n'])},m={int(row['m'])},i={int(row['i'])} → S1={s1_avg:.1f} S2={s2_avg:.1f} S3={s3_avg:.1f}")

    # Best strategy per configuration
    print("\nBest strategy per configuration:")
    for _, row in df.iterrows():
        wins = {"S1(Random)": row.get("s1_wins", 0) or 0,
                "S2(Adaptive)": row.get("s2_wins", 0) or 0,
                "S3(Fixed)": row.get("s3_wins", 0) or 0}
        best = max(wins, key=wins.get)
        total = sum(wins.values())
        print(f"  n={int(row['n'])}, m={int(row['m'])}, i={int(row['i'])} → {best} ({wins[best]:.0f}/{total} wins = {100*wins[best]/total:.1f}%)")

    # Fairness metrics
    if "gini" in df.columns:
        print("\nFairness (Gini coefficient, 0=perfect equality, 1=maximum inequality):")
        for _, row in df.iterrows():
            gini = row.get("gini")
            std = row.get("stddev")
            if gini is not None:
                print(f"  n={int(row['n'])},m={int(row['m'])},i={int(row['i'])} → Gini={gini:.3f}, StdDev={std:.2f}, CV={row.get('cv',0):.3f}")

    # Strategy significance
    sig_results = strategy_significance(df)
    print("\nStatistical significance (Chi-square test, α=0.05):")
    for r in sig_results:
        if r.get("p_value") is not None:
            sig = "SIGNIFICANT" if r["significant"] else "not significant"
            print(f"  n={r['n']},m={r['m']},i={r['i']} → χ²={r['chi2']:.4f}, p={r['p_value']:.6f} [{sig}]")
        else:
            print(f"  n={r['n']},m={r['m']},i={r['i']} → {r.get('note', 'N/A')}")

    # Convergence analysis
    conv = convergence_analysis(df)
    print("\nStrategy 2 (Adaptive) convergence analysis:")
    print(conv.to_string(index=False, float_format="{:.4f}".format))

# ── Charts ───────────────────────────────────────────────────
def plot_charts(df: pd.DataFrame, out_dir: str):
    if df.empty:
        return

    fig = plt.figure(figsize=(20, 20))
    fig.suptitle("Contract Net Protocol – Metric Analysis", fontsize=16, fontweight="bold")
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.4, wspace=0.4)

    configs = [f"n={int(r['n']) if pd.notna(r.get('n')) else '?'}\nm={int(r['m']) if pd.notna(r.get('m')) else '?'},i={int(r['i']) if pd.notna(r.get('i')) else '?'}"
               for _, r in df.iterrows()]
    x = range(len(df))

    def safe_col(col, default=0):
        return df[col].fillna(default) if col in df.columns else pd.Series([default]*len(df))

    # 1. % of theoretical max value
    ax1 = fig.add_subplot(gs[0, 0])
    pct_vals = safe_col("pct")
    bars = ax1.bar(x, pct_vals, color="#4C72B0", edgecolor="white")
    ax1.set_xticks(x); ax1.set_xticklabels(configs, fontsize=7)
    ax1.set_ylabel("% of theoretical max value")
    ax1.set_title("Efficiency (% Theoretical Max Value)")
    ax1.set_ylim(0, 110)
    for bar, val in zip(bars, pct_vals):
        if pd.notna(val):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                     f"{val:.1f}%", ha="center", va="bottom", fontsize=7)

    # 2. Contracts awarded vs failed
    ax2 = fig.add_subplot(gs[0, 1])
    awarded_vals = safe_col("awarded")
    failed_vals = safe_col("failed")
    ax2.bar(x, awarded_vals, label="Awarded", color="#55A868")
    ax2.bar(x, failed_vals, label="Failed", color="#C44E52", bottom=awarded_vals)
    ax2.set_xticks(x); ax2.set_xticklabels(configs, fontsize=7)
    ax2.set_ylabel("Number of contracts")
    ax2.set_title("Contracts: Awarded vs Failed")
    ax2.legend(fontsize=8)

    # 3. Strategy wins comparison (stacked bar)
    ax3 = fig.add_subplot(gs[0, 2])
    s1_vals = safe_col("s1_wins")
    s2_vals = safe_col("s2_wins")
    s3_vals = safe_col("s3_wins")
    ax3.bar(x, s1_vals, label="S1 Random",   color="#4C72B0")
    ax3.bar(x, s2_vals, label="S2 Adaptive", color="#DD8452", bottom=s1_vals)
    ax3.bar(x, s3_vals, label="S3 Fixed",    color="#55A868", bottom=s1_vals+s2_vals)
    ax3.set_xticks(x); ax3.set_xticklabels(configs, fontsize=7)
    ax3.set_ylabel("Wins")
    ax3.set_title("Strategy Wins Breakdown")
    ax3.legend(fontsize=8)

    # 4. Average value per win per strategy
    ax4 = fig.add_subplot(gs[1, 0])
    w = 0.25
    xs = list(x)
    ax4.bar([xi - w for xi in xs], safe_col("s1_avg"), width=w, label="S1 Random",   color="#4C72B0")
    ax4.bar([xi       for xi in xs], safe_col("s2_avg"), width=w, label="S2 Adaptive", color="#DD8452")
    ax4.bar([xi + w for xi in xs], safe_col("s3_avg"), width=w, label="S3 Fixed",    color="#55A868")
    ax4.set_xticks(xs); ax4.set_xticklabels(configs, fontsize=7)
    ax4.set_ylabel("Avg value per win")
    ax4.set_title("Avg Contract Value by Strategy")
    ax4.legend(fontsize=8)

    # 5. Avg contracts per initiator
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.plot(range(len(df)), safe_col("avg_contracts"), marker="o", color="#4C72B0", linewidth=2)
    ax5.set_xticks(range(len(df))); ax5.set_xticklabels(configs, fontsize=7)
    ax5.set_ylabel("Avg contracts per initiator")
    ax5.set_title("Avg Contracts Won per Initiator")
    ax5.grid(True, linestyle="--", alpha=0.5)

    # 6. % of theoretical max vs n (varying m, i fixed or averaged)
    ax6 = fig.add_subplot(gs[1, 2])
    if "m" in df.columns and "i" in df.columns:
        for mi_combo, grp in df.groupby(["m","i"]):
            label = f"m={int(mi_combo[0])},i={int(mi_combo[1])}"
            ax6.plot(grp["n"], grp["pct"], marker="s", label=label, linewidth=2)
    ax6.set_xlabel("n (initiators)")
    ax6.set_ylabel("% theoretical max")
    ax6.set_title("Efficiency vs Number of Initiators")
    ax6.legend(fontsize=7)
    ax6.grid(True, linestyle="--", alpha=0.5)

    # 7. Avg award latency
    ax7 = fig.add_subplot(gs[2, 0])
    ax7.bar(x, safe_col("avg_latency"), color="#DA5C5C", edgecolor="white")
    ax7.set_xticks(x); ax7.set_xticklabels(configs, fontsize=7)
    ax7.set_ylabel("ms")
    ax7.set_title("Avg Award Latency (ms)")
    ax7.grid(True, linestyle="--", alpha=0.5)

    # 8. Proposal arrival rate
    ax8 = fig.add_subplot(gs[2, 1])
    ax8.bar(x, safe_col("proposal_rate"), color="#8E44AD", edgecolor="white")
    ax8.set_xticks(x); ax8.set_xticklabels(configs, fontsize=7)
    ax8.set_ylabel("proposals/s")
    ax8.set_title("Proposal Arrival Rate")
    ax8.grid(True, linestyle="--", alpha=0.5)

    # 9. Per-strategy avg winning price
    ax9 = fig.add_subplot(gs[2, 2])
    w = 0.25
    xs = list(x)
    s1_avgs = [df["s1_avg_win"].iloc[i] if "s1_avg_win" in df.columns and pd.notna(df["s1_avg_win"].iloc[i]) else 0 for i in range(len(df))]
    s2_avgs = [df["s2_avg_win"].iloc[i] if "s2_avg_win" in df.columns and pd.notna(df["s2_avg_win"].iloc[i]) else 0 for i in range(len(df))]
    s3_avgs = [df["s3_avg_win"].iloc[i] if "s3_avg_win" in df.columns and pd.notna(df["s3_avg_win"].iloc[i]) else 0 for i in range(len(df))]
    ax9.bar([xi - w for xi in xs], s1_avgs, width=w, label="S1 Random",   color="#4C72B0")
    ax9.bar([xi       for xi in xs], s2_avgs, width=w, label="S2 Adaptive", color="#DD8452")
    ax9.bar([xi + w for xi in xs], s3_avgs, width=w, label="S3 Fixed",    color="#55A868")
    ax9.set_xticks(xs); ax9.set_xticklabels(configs, fontsize=7)
    ax9.set_ylabel("Avg winning price")
    ax9.set_title("Avg Winning Price by Strategy")
    ax9.legend(fontsize=8)
    ax9.grid(True, linestyle="--", alpha=0.5)

    out_path = os.path.join(out_dir, "cnp_analysis.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to: {out_path}")
    plt.close()

def plot_fairness(df: pd.DataFrame, out_dir: str):
    """Plot fairness metrics (Gini, StdDev) across configurations."""
    if "gini" not in df.columns or df.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Fairness Analysis", fontsize=14, fontweight="bold")

    x = range(len(df))
    configs = [f"n={int(r['n']) if pd.notna(r.get('n')) else '?'},m={int(r['m']) if pd.notna(r.get('m')) else '?'},i={int(r['i']) if pd.notna(r.get('i')) else '?'}"
               for _, r in df.iterrows()]

    ax1, ax2 = axes

    # Gini coefficient
    gini_vals = df["gini"].fillna(0)
    bars1 = ax1.bar(x, gini_vals, color="#9370DB", edgecolor="white")
    ax1.set_xticks(x); ax1.set_xticklabels(configs, fontsize=7)
    ax1.set_ylabel("Gini coefficient")
    ax1.set_title("Gini Coefficient (0=equal, 1=unequal)")
    ax1.set_ylim(0, 1)
    for bar, val in zip(bars1, gini_vals):
        if pd.notna(val):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                     f"{val:.3f}", ha="center", va="bottom", fontsize=7)

    # StdDev of contracts per initiator
    std_vals = df["stddev"].fillna(0)
    bars2 = ax2.bar(x, std_vals, color="#20B2AA", edgecolor="white")
    ax2.set_xticks(x); ax2.set_xticklabels(configs, fontsize=7)
    ax2.set_ylabel("StdDev")
    ax2.set_title("StdDev of Contracts per Initiator")
    ax2.grid(True, linestyle="--", alpha=0.5)
    for bar, val in zip(bars2, std_vals):
        if pd.notna(val):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                     f"{val:.2f}", ha="center", va="bottom", fontsize=7)

    out_path = os.path.join(out_dir, "cnp_fairness.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Fairness chart: {out_path}")
    plt.close()

# ── Main ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Analyse CNP experiment results")
    parser.add_argument("--dir", default=".", help="Directory with cnp_report_*.txt files")
    parser.add_argument("--export-csv", action="store_true", help="Export summary data as CSV")
    parser.add_argument("--export-json", action="store_true", help="Export summary data as JSON")
    parser.add_argument("--output-prefix", default="cnp_analysis", help="Prefix for exported files")
    args = parser.parse_args()

    df = load_all_reports(args.dir)
    if df.empty:
        print("No data to analyse.")
        return

    # Compute fairness metrics
    df = compute_fairness(df)

    print_table(df)
    plot_charts(df, args.dir)
    plot_fairness(df, args.dir)

    if args.export_csv:
        export_csv(df, args.dir, args.output_prefix)
    if args.export_json:
        export_json(df, args.dir, args.output_prefix)

if __name__ == "__main__":
    main()