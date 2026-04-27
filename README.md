# Contract Net Protocol (CNP) - JaCaMo Implementation

## Overview

This project implements a Contract Net Protocol (CNP) scenario using JaCaMo (Jason + CArtAgO + Moise).

- Initiators request services.
- Participants reply with proposals based on one of three strategies.
- The initiator filters proposals by threshold, sorts the below-threshold proposals by value (ascending), and accepts up to 10 lowest offers per contract.

## Current Policy (Implemented)

- Initiators: `0 < n <= 200`
- Participants: `0 < m <= 50`
- Parallel contracts per initiator: `0 < i <= 10`
- Recommended default configuration in this repository: `n=50`, `m=10`, `i=10`

For each contract, an initiator:
1. Broadcasts CFP to all participants.
2. Waits for proposals (`timeout_ms`, default `3000` ms).
3. Filters proposals by threshold — only proposals with value ≤ `price_threshold` proceed to evaluation.
4. Sorts below-threshold proposals by value (lowest first).
5. Accepts up to 10 lowest proposals (or all if fewer than 10 pass the threshold).
6. Rejects the remaining proposals.

After finishing all `i` contracts, the initiator marks itself as unavailable.

Each initiator is assigned a random `price_threshold` drawn from `[threshold_min, threshold_max]` (default `[80, 150]`).

Accepted participants simulate service execution with a small delay (`service_timeout_ms`, default `200` ms).

## Project Structure

```
cnp_project/
|- cnp_project.jcm                # Main JaCaMo project file
|- generate_cnp_jcm.py            # Generator for (n, m, i) configurations
|- analyse_metrics.py             # Parser/plotter for cnp_report_*.txt
|- src/
|  |- agt/
|  |  |- initiator.asl
|  |  |- participant_strategy1.asl
|  |  |- participant_strategy2.asl
|  |  |- participant_strategy3.asl
|  |- env/example/
|     |- MetricsBoard.java
```

## Agent Behaviors

### Initiator

- Launches `i` contracts concurrently (`!!run_cnp(...)`).
- Uses contract IDs as:

```text
ContractId = initiator_id * 1000 + local_contract_number
```

- Receives proposals via message source annotation and stores bids as `(value, sender)`.
- Filters proposals into `Below` (value ≤ threshold) and `Above` (value > threshold).
- From `Below`, selects up to 10 minimum-value bids.
- Sends `award` to selected participants and `reject` to the rest.
- Waits `service_receive_timeout_ms` (default `200` ms) before closing contract.
- Becomes unavailable after all own contracts are finished.

### Participant Strategy 1 (Random Variation)

```text
price = base_price + random(-20%, +20%)
```

### Participant Strategy 2 (Adaptive Discount)

```text
price = base_price - (rejected_count * discount)
```

### Participant Strategy 3 (Fixed Price)

```text
price = fixed_price
```

## Message Flow (Current)

```text
Initiator                          Participant_k
    |                                   |
    |---- tell cfp(CId, AgId, Req) ---->|
    |                                   | (compute strategy price)
    |<--- tell proposal(CId, Price) ----| [source(Participant_k)]
    |                                   |
    | (filter by threshold, sort ascending, pick up to 10)
    |---- tell award(CId, Price) ------>| selected participants
    |---- tell reject(CId) ------------>| non-selected participants
```

## Configuration Generator

Generate a new project file:

```bash
python3 generate_cnp_jcm.py --n 50 --m 10 --i 10 --out cnp_project.jcm
```

Defaults:

- `n=50`
- `m=10`
- `i=10`
- `out=cnp_project.jcm`
- `threshold-min=80`
- `threshold-max=150`

Participant distribution is automatic:

- Strategy 1: `1 .. ceil(m/3)`
- Strategy 2: `ceil(m/3)+1 .. ceil(2m/3)`
- Strategy 3: `ceil(2m/3)+1 .. m`

## Run

Run the current configuration:

```bash
./gradlew run --no-daemon --console=plain
```

## Stability Notes

- High values of `n` and `m` can overload message traffic and runtime resources.
- If your machine is unstable at larger scales, start with smaller values (for example `n=20, m=10, i=5`) and scale up.
- If needed, increase `timeout_ms` in `initiator.asl`.

## Metrics and Analysis

- The `MetricsBoard` artifact is instantiated from the `.jcm` file.
- It tracks: total awarded/failed contracts, total value, per-strategy wins/values, per-initiator stats, threshold rejection counts, award latency, and proposal arrival rate.
- Observable properties are updated in real-time for live monitoring.
- A final report is written to `cnp_report_YYYYMMDD_HHmmss.txt`.
- `analyse_metrics.py` expects report files matching `cnp_report_*.txt`.

## Dependencies

- JaCaMo `1.3.0` (via Gradle dependency)
- Java 11+
- Python 3.9+ (for analysis)
- Python packages: `pandas`, `matplotlib`