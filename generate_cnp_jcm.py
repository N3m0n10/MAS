#!/usr/bin/env python3
"""
generate_cnp_jcm.py
====================
Generates a JaCaMo .jcm file for the Contract Net Protocol experiment
given n initiators, m participants, and i parallel contracts per initiator.

Usage:
    python generate_cnp_jcm.py --n 50 --m 10 --i 10 --out cnp_project.jcm
    python generate_cnp_jcm.py --n 50 --m 10 --i 10 --threshold-min 80 --threshold-max 150

Participant distribution (m agents split equally across 3 strategies):
    Strategy 1: agents 1 … ceil(m/3)
    Strategy 2: agents ceil(m/3)+1 … ceil(2m/3)
    Strategy 3: agents ceil(2m/3)+1 … m

Constraints:
    0 < n <= 200
    0 < m <= 50
    0 < i <= 10
"""

import argparse
import math
import random

def generate(n: int, m: int, i: int, out: str,
             threshold_min: int = 80, threshold_max: int = 150):
    assert 0 < n < 201, "n must satisfy 0 < n <= 200"
    assert 0 < m < 51,  "m must satisfy 0 < m <= 50"
    assert 0 < i < 11,  "i must satisfy 0 < i <= 10"
    assert 0 < threshold_min <= threshold_max, "threshold_min must be > 0 and <= threshold_max"

    # Split m participants into 3 strategies as evenly as possible
    s1_end = math.ceil(m / 3)
    s2_end = math.ceil(2 * m / 3)
    s3_end = m

    # Build strategy map for MetricsBoard (participantId:strategy;...)
    strategy_parts = []
    for k in range(1, s1_end + 1):
        strategy_parts.append(f"{k}:1")
    for k in range(s1_end + 1, s2_end + 1):
        strategy_parts.append(f"{k}:2")
    for k in range(s2_end + 1, s3_end + 1):
        strategy_parts.append(f"{k}:3")
    strategy_map = ";".join(strategy_parts)

    lines = []
    lines.append("// Contract Net Protocol – Auto-generated JaCaMo project")
    lines.append(f"// Configuration: n={n} initiators, m={m} participants, i={i} contracts/initiator")
    lines.append(f"// Threshold range: [{threshold_min}, {threshold_max}]")
    lines.append(f"// Theoretical max contracts : {n * i}")
    lines.append(f"// Theoretical max value     : {n * i * 200}  (service_value=200)")
    lines.append("")

    # Build strategy map string for MetricsBoard
    # Escape quotes for JCM file embedding
    strategy_map_escaped = strategy_map.replace('"', '\\"')

    lines.append("mas cnp {")
    lines.append("")
    lines.append(f"    // === {n} initiator(s), each runs {i} CNPs in parallel ===")

    for idx in range(1, n + 1):
        threshold = random.randint(threshold_min, threshold_max)
        lines.append(f"    agent initiator{idx} : initiator.asl {{")
        lines.append(f"        join: cnp_workspace")
        lines.append(f"        focus: cnp_workspace.metrics_board")
        lines.append(f"        beliefs: agent_id({idx}), num_contracts({i}), num_participants({m}), price_threshold({threshold})")
        lines.append(f"    }}")

    lines.append("")
    lines.append(f"    // === {m} participant(s) across 3 strategies ===")

    # Strategy 1 participants (random price variation)
    lines.append(f"    // Strategy 1: Random price variation ({s1_end} agents)")
    BASE_PRICES_S1 = [100, 120, 90, 110, 105, 95, 115, 108, 102, 118,
                      98, 112, 122, 88, 107, 103, 117, 93, 125, 96]
    for k in range(1, s1_end + 1):
        bp = BASE_PRICES_S1[(k - 1) % len(BASE_PRICES_S1)]
        lines.append(f"    agent participant{k} : participant_strategy1.asl {{")
        lines.append(f"        join: cnp_workspace")
        lines.append(f"        focus: cnp_workspace.metrics_board")
        lines.append(f"        beliefs: agent_id({k}), base_price({bp})")
        lines.append(f"    }}")

    # Strategy 2 participants (adaptive discount)
    lines.append(f"    // Strategy 2: Adaptive discount ({s2_end - s1_end} agents)")
    BASE_PRICES_S2 = [115, 125, 100, 130, 108, 120, 140, 95, 135, 118,
                      128, 105, 122, 112, 132, 98, 145, 103, 138, 110]
    DISCOUNTS_S2   = [5, 8, 3, 10, 6, 7, 4, 9, 5, 8,
                      6, 3, 7, 5, 10, 4, 9, 6, 8, 5]
    for k in range(s1_end + 1, s2_end + 1):
        idx = k - s1_end - 1
        bp  = BASE_PRICES_S2[idx % len(BASE_PRICES_S2)]
        disc = DISCOUNTS_S2[idx % len(DISCOUNTS_S2)]
        lines.append(f"    agent participant{k} : participant_strategy2.asl {{")
        lines.append(f"        join: cnp_workspace")
        lines.append(f"        focus: cnp_workspace.metrics_board")
        lines.append(f"        beliefs: agent_id({k}), base_price({bp}), discount({disc})")
        lines.append(f"    }}")

    # Strategy 3 participants (fixed price)
    lines.append(f"    // Strategy 3: Fixed price ({s3_end - s2_end} agents)")
    FIXED_PRICES = [95, 105, 100, 110, 98, 102, 108, 97, 112, 103,
                    106, 99, 115, 101, 107, 96, 111, 104, 109, 94]
    for k in range(s2_end + 1, s3_end + 1):
        idx = k - s2_end - 1
        fp  = FIXED_PRICES[idx % len(FIXED_PRICES)]
        lines.append(f"    agent participant{k} : participant_strategy3.asl {{")
        lines.append(f"        join: cnp_workspace")
        lines.append(f"        focus: cnp_workspace.metrics_board")
        lines.append(f"        beliefs: agent_id({k}), fixed_price({fp})")
        lines.append(f"    }}")

    lines.append("")
    lines.append("    // === Control agent: triggers final report ===")
    lines.append(f"    agent report_controller : report_controller.asl {{")
    lines.append(f"        join: cnp_workspace")
    lines.append(f"        focus: cnp_workspace.metrics_board")
    lines.append(f"        beliefs: num_initiators({n}), total_contracts({n * i})")
    lines.append(f"    }}")

    lines.append("")
    lines.append("    workspace cnp_workspace {")
    lines.append(f"        artifact metrics_board : example.MetricsBoard({n}, {m}, {i}, \"{strategy_map_escaped}\")")
    lines.append("    }")
    lines.append("")
    lines.append('    asl-path: "src/agt"')
    lines.append("}")
    lines.append("")

    content = "\n".join(lines)
    with open(out, "w") as f:
        f.write(content)
    print(f"Generated: {out}")
    print(f"  n={n} initiators | m={m} participants | i={i} contracts each")
    print(f"  Threshold range: [{threshold_min}, {threshold_max}] (random per initiator)")
    print(f"  Strategy 1: participants 1–{s1_end}")
    print(f"  Strategy 2: participants {s1_end+1}–{s2_end}")
    print(f"  Strategy 3: participants {s2_end+1}–{s3_end}")
    print(f"  Theoretical max contracts : {n * i}")
    print(f"  Theoretical max value     : {n * i * 200}")
    print(f"  Strategy map: {strategy_map}")


def main():
    parser = argparse.ArgumentParser(description="Generate .jcm configuration for CNP experiment")
    parser.add_argument("--n",   type=int, default=50, help="Number of initiators (0<n<=200)")
    parser.add_argument("--m",   type=int, default=10, help="Number of participants (0<m<=50)")
    parser.add_argument("--i",   type=int, default=10, help="Contracts per initiator (0<i<=10)")
    parser.add_argument("--out", type=str, default="cnp_project.jcm", help="Output filename")
    parser.add_argument("--threshold-min", type=int, default=80,
                        help="Minimum price threshold per initiator (default 80)")
    parser.add_argument("--threshold-max", type=int, default=150,
                        help="Maximum price threshold per initiator (default 150)")
    args = parser.parse_args()
    generate(args.n, args.m, args.i, args.out,
             args.threshold_min, args.threshold_max)


if __name__ == "__main__":
    main()