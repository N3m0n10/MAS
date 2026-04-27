// ============================================================
//  MetricsBoard.java  –  CArtAgO Artifact
//
//  Central metrics collector for the CNP experiment.
//  Tracks:
//    • Total contracts awarded / failed
//    • Total value of awarded contracts
//    • Per-strategy wins and values
//    • Per-initiator contract counts
//
//  Observable properties are updated in real-time so any
//  agent focusing on this artifact can react to changes.
//
//  NOTE: All @OPERATION parameters use double to match Jason 3.x
//  internal type. Integer values passed from ASL are cast internally.
// ============================================================

package example;

import cartago.*;
import java.util.*;
import java.io.*;
import java.time.*;
import java.time.format.*;

public class MetricsBoard extends Artifact {

    // Config
    private int numInitiators;
    private int numParticipants;
    private int contractsPerInitiator;
    private int theoreticalMaxContracts;    // n * i
    private double theoreticalMaxValue;     // n * i * service_value (200)
    private static final int SERVICE_VALUE = 200;

    // Counters
    private int totalAwarded   = 0;
    private int totalFailed    = 0;
    private double totalValue  = 0.0;

    // Threshold filter metrics
    private int totalThresholdRejections = 0;

    // Latency / throughput metrics
    private long totalAwardTimeMs = 0;
    private int awardTimeCount = 0;
    private int totalProposalsReceived = 0;

    // Per-strategy wins and values
    private int[]    strategyWins   = new int[4];    // index 1-3
    private double[] strategyValues = new double[4];

    // Per-strategy avg winning price
    private double[] strategyAvgWinningPrice = new double[4];
    private int[]    strategyAwardCount = new int[4];

    // Per-initiator
    private Map<Integer, Integer> initiatorContracts = new HashMap<>();
    private Map<Integer, Double>  initiatorValues    = new HashMap<>();

    // Participant rejection tracker (strategy 2 support)
    private Map<String, Integer> participantRejections = new HashMap<>();

    // Participant strategy map: participantId -> strategy (1, 2, or 3)
    private Map<Integer, Integer> participantStrategy = new HashMap<>();

    // Timestamp
    private long startTime;

    // ── init ────────────────────────────────────────────────
    void init(int n, int m, int i) {
        init(n, m, i, "");
    }

    void init(int n, int m, int i, String strategyMap) {
        this.numInitiators          = n;
        this.numParticipants        = m;
        this.contractsPerInitiator  = i;
        this.theoreticalMaxContracts = n * i;
        this.theoreticalMaxValue    = theoreticalMaxContracts * SERVICE_VALUE;
        this.startTime              = System.currentTimeMillis();

        // Parse strategy map if provided (format: "participantId:strategy;...")
        if (strategyMap != null && !strategyMap.isEmpty()) {
            for (String entry : strategyMap.split(";")) {
                String[] parts = entry.split(":");
                if (parts.length == 2) {
                    try {
                        int pid = Integer.parseInt(parts[0].trim());
                        int strat = Integer.parseInt(parts[1].trim());
                        participantStrategy.put(pid, strat);
                    } catch (NumberFormatException e) {
                        // ignore malformed entries
                    }
                }
            }
        }

        // Observable properties
        defineObsProperty("total_awarded",   0);
        defineObsProperty("total_failed",    0);
        defineObsProperty("total_value",     0.0);
        defineObsProperty("pct_theoretical", 0.0);   // % of max theoretical value
        defineObsProperty("strategy1_wins",  0);
        defineObsProperty("strategy2_wins",  0);
        defineObsProperty("strategy3_wins",  0);
        defineObsProperty("strategy1_value", 0.0);
        defineObsProperty("strategy2_value", 0.0);
        defineObsProperty("strategy3_value", 0.0);
        defineObsProperty("threshold_rejections", 0);
        defineObsProperty("pct_threshold_rejections", 0.0);
        defineObsProperty("avg_award_time_ms", 0.0);
        defineObsProperty("proposal_arrival_rate", 0.0);
        defineObsProperty("avg_win_price_s1", 0.0);
        defineObsProperty("avg_win_price_s2", 0.0);
        defineObsProperty("avg_win_price_s3", 0.0);

        System.out.println("[MetricsBoard] Initialized: n=" + n +
                           ", m=" + m + ", i=" + i +
                           ", theoreticalMax=" + theoreticalMaxContracts +
                           " contracts / " + theoreticalMaxValue + " value");
    }

    // ── awarded_contract ────────────────────────────────────
    @OPERATION
    void awarded_contract(double contractId, double initiatorId,
                          String winner, double value) {
        awarded_contract(contractId, initiatorId, winner, value, -1);
    }

    @OPERATION
    void awarded_contract(double contractId, double initiatorId,
                          String winner, double value, double participantId) {
        totalAwarded++;
        totalValue += value;

        int cId = (int) contractId;
        int iId = (int) initiatorId;
        int pId = (int) participantId;

        // Per-initiator
        initiatorContracts.merge(iId, 1, Integer::sum);
        initiatorValues.merge(iId, value, Double::sum);

        // Detect strategy from winner name and/or participant id
        int strat = detectStrategy(winner, pId);
        if (strat >= 1 && strat <= 3) {
            strategyWins[strat]++;
            strategyValues[strat] += value;
        }

        updateObsProperties();
        printLiveStats();
    }

    // ── failed_contract ─────────────────────────────────────
    @OPERATION
    void failed_contract(double contractId, double initiatorId) {
        totalFailed++;
        updateObsProperties();
        System.out.println("[MetricsBoard] ⚠ Contract #" + (int)contractId +
                           " (initiator " + (int)initiatorId + ") FAILED – no proposals.");
    }

    // ── record_threshold_rejection ────────────────────────────
    @OPERATION
    void record_threshold_rejection(double contractId, double initiatorId, double price) {
        totalThresholdRejections++;
        updateObsProperties();
        System.out.println("[MetricsBoard] Contract #" + (int)contractId +
                           " (initiator " + (int)initiatorId +
                           ") THRESHOLD REJECTED price=" + price);
    }

    // ── record_award_time ─────────────────────────────────────
    @OPERATION
    void record_award_time(double contractId, double awardTimeMs) {
        totalAwardTimeMs += (long) awardTimeMs;
        awardTimeCount++;
        updateObsProperties();
    }

    // ── record_proposal_count ──────────────────────────────────
    @OPERATION
    void record_proposal_count(double contractId, double initiatorId, double proposalCount) {
        totalProposalsReceived += (int) proposalCount;
        updateObsProperties();
    }

    // ── record_winning_price ───────────────────────────────────
    @OPERATION
    void record_winning_price(double contractId, String winner, double price) {
        int strat = detectStrategy(winner);
        if (strat >= 1 && strat <= 3) {
            strategyAwardCount[strat]++;
            strategyAvgWinningPrice[strat] =
                ((strategyAvgWinningPrice[strat] * (strategyAwardCount[strat] - 1)) + price)
                / strategyAwardCount[strat];
        }
        updateObsProperties();
    }

    // ── participant_won ─────────────────────────────────────
    @OPERATION
    void participant_won(double participantId, double contractId,
                         double value, String strategy) {
        // Already counted via awarded_contract; this is for participant-side logging
        updateObsProperties();
        System.out.println("[MetricsBoard] Participant " + (int)participantId +
                           " (" + strategy + ") WON #" + (int)contractId +
                           " value=" + value);
    }

    // ── participant_rejected ─────────────────────────────────
    @OPERATION
    void participant_rejected(double participantId, double contractId, String strategy) {
        String key = strategy + "_" + (int)participantId;
        participantRejections.merge(key, 1, Integer::sum);
        updateObsProperties();
        System.out.println("[MetricsBoard] Participant " + (int)participantId +
                           " (" + strategy + ") REJECTED #" + (int)contractId +
                           " (total rejections=" +
                           participantRejections.get(key) + ")");
    }

    // ── print_report ─────────────────────────────────────────
    @OPERATION
    void print_report() {
        long elapsed = System.currentTimeMillis() - startTime;
        double pct = theoreticalMaxValue > 0
                     ? (totalValue / theoreticalMaxValue) * 100.0 : 0.0;

        double pctThreshold = totalProposalsReceived > 0
                     ? ((double) totalThresholdRejections / totalProposalsReceived) * 100.0 : 0.0;

        double avgAwardTime = awardTimeCount > 0
                      ? (double) totalAwardTimeMs / awardTimeCount : 0.0;

        double proposalArrivalRate = elapsed > 0
                      ? (double) totalProposalsReceived / (elapsed / 1000.0) : 0.0;

        StringBuilder sb = new StringBuilder();
        sb.append("\n╔══════════════════════════════════════════════════════╗\n");
        sb.append(  "║          CONTRACT NET PROTOCOL – FINAL REPORT        ║\n");
        sb.append(  "╠══════════════════════════════════════════════════════╣\n");
        sb.append(String.format("║  Configuration: n=%d initiators, m=%d participants%n",
                                numInitiators, numParticipants));
        sb.append(String.format("║                 i=%d contracts/initiator%n",
                                contractsPerInitiator));
        sb.append(String.format("║  Elapsed time : %.2f s%n", elapsed / 1000.0));
        sb.append(  "╠══════════════════════════════════════════════════════╣\n");
        sb.append(String.format("║  Theoretical max contracts : %d%n",
                                theoreticalMaxContracts));
        sb.append(String.format("║  Theoretical max value     : %.0f%n",
                                theoreticalMaxValue));
        sb.append(  "╠══════════════════════════════════════════════════════╣\n");
        sb.append(String.format("║  Contracts AWARDED : %d / %d%n",
                                totalAwarded, theoreticalMaxContracts));
        sb.append(String.format("║  Contracts FAILED  : %d%n", totalFailed));
        sb.append(String.format("║  Total value       : %.2f%n", totalValue));
        sb.append(String.format("║  %% of theoretical  : %.2f %%%n", pct));
        sb.append(  "╠══════════════════════════════════════════════════════╣\n");
        sb.append(String.format("║  Threshold Rejections: %d / %d proposals (%.1f %%)%n",
                                totalThresholdRejections, totalProposalsReceived, pctThreshold));
        sb.append(String.format("║  Avg award latency  : %.1f ms%n", avgAwardTime));
        sb.append(String.format("║  Proposal arrival  : %.2f proposals/s%n", proposalArrivalRate));
        sb.append(  "╠══════════════════════════════════════════════════════╣\n");

        // Strategy breakdown
        double[] avgVals = new double[4];
        for (int s = 1; s <= 3; s++) {
            avgVals[s] = strategyWins[s] > 0
                         ? strategyValues[s] / strategyWins[s] : 0.0;
        }
        sb.append("║  Strategy Analysis:%n");
        sb.append(String.format("║    S1 (Random)    wins=%d  total=%.0f  avg=%.1f  avg_win=%.1f%n",
                                strategyWins[1], strategyValues[1], avgVals[1], strategyAvgWinningPrice[1]));
        sb.append(String.format("║    S2 (Adaptive)  wins=%d  total=%.0f  avg=%.1f  avg_win=%.1f%n",
                                strategyWins[2], strategyValues[2], avgVals[2], strategyAvgWinningPrice[2]));
        sb.append(String.format("║    S3 (Fixed)     wins=%d  total=%.0f  avg=%.1f  avg_win=%.1f%n",
                                strategyWins[3], strategyValues[3], avgVals[3], strategyAvgWinningPrice[3]));

        // Best strategy
        int bestStrat = 1;
        for (int s = 2; s <= 3; s++) {
            if (strategyWins[s] > strategyWins[bestStrat]) bestStrat = s;
        }
        sb.append(String.format("║  ► Most wins: Strategy %d%n", bestStrat));

        sb.append(  "╠══════════════════════════════════════════════════════╣\n");

        // Per-initiator stats
        sb.append("║  Per-Initiator Contracts Won:%n");
        int totalFromInitiators = 0;
        for (Map.Entry<Integer, Integer> e : initiatorContracts.entrySet()) {
            int iid = e.getKey();
            int cnt = e.getValue();
            double val = initiatorValues.getOrDefault(iid, 0.0);
            double avg = cnt > 0 ? val / cnt : 0.0;
            sb.append(String.format("║    Initiator %d: %d contracts, value=%.0f, avg=%.1f%n",
                                    iid, cnt, val, avg));
            totalFromInitiators += cnt;
        }
        double avgContractsPerInitiator = numInitiators > 0
                ? (double) totalFromInitiators / numInitiators : 0.0;
        sb.append(String.format("║  Avg contracts/initiator: %.2f%n",
                                avgContractsPerInitiator));

        sb.append(  "╠══════════════════════════════════════════════════════╣\n");
        // Top 3 rejected participants
        sb.append("║  Top Rejected Participants (Strategy 2):%n");
        participantRejections.entrySet().stream()
            .filter(e -> e.getKey().startsWith("strategy2"))
            .sorted(Map.Entry.<String,Integer>comparingByValue().reversed())
            .limit(3)
            .forEach(e -> sb.append(String.format("║    %s: %d rejections%n",
                                    e.getKey(), e.getValue())));

        sb.append("╚══════════════════════════════════════════════════════╝\n");

        System.out.println(sb.toString());

        // Write to file
        writeReportToFile(sb.toString());
    }

    // ── helpers ──────────────────────────────────────────────

    private void updateObsProperties() {
        double pct = theoreticalMaxValue > 0
                     ? (totalValue / theoreticalMaxValue) * 100.0 : 0.0;

        double pctThreshold = totalProposalsReceived > 0
                     ? ((double) totalThresholdRejections / totalProposalsReceived) * 100.0 : 0.0;

        double avgAwardTime = awardTimeCount > 0
                      ? (double) totalAwardTimeMs / awardTimeCount : 0.0;

        long elapsed = System.currentTimeMillis() - startTime;
        double proposalArrivalRate = elapsed > 0
                      ? (double) totalProposalsReceived / (elapsed / 1000.0) : 0.0;

        getObsProperty("total_awarded").updateValue(totalAwarded);
        getObsProperty("total_failed").updateValue(totalFailed);
        getObsProperty("total_value").updateValue(totalValue);
        getObsProperty("pct_theoretical").updateValue(pct);
        getObsProperty("strategy1_wins").updateValue(strategyWins[1]);
        getObsProperty("strategy2_wins").updateValue(strategyWins[2]);
        getObsProperty("strategy3_wins").updateValue(strategyWins[3]);
        getObsProperty("strategy1_value").updateValue(strategyValues[1]);
        getObsProperty("strategy2_value").updateValue(strategyValues[2]);
        getObsProperty("strategy3_value").updateValue(strategyValues[3]);
        getObsProperty("threshold_rejections").updateValue(totalThresholdRejections);
        getObsProperty("pct_threshold_rejections").updateValue(pctThreshold);
        getObsProperty("avg_award_time_ms").updateValue(avgAwardTime);
        getObsProperty("proposal_arrival_rate").updateValue(proposalArrivalRate);
        getObsProperty("avg_win_price_s1").updateValue(strategyAvgWinningPrice[1]);
        getObsProperty("avg_win_price_s2").updateValue(strategyAvgWinningPrice[2]);
        getObsProperty("avg_win_price_s3").updateValue(strategyAvgWinningPrice[3]);
    }

    private void printLiveStats() {
        double pct = theoreticalMaxValue > 0
                     ? (totalValue / theoreticalMaxValue) * 100.0 : 0.0;
        System.out.printf("[MetricsBoard] awarded=%d/%d | failed=%d | " +
                          "value=%.0f | pct=%.1f%% | S1=%d S2=%d S3=%d%n",
                          totalAwarded, theoreticalMaxContracts,
                          totalFailed, totalValue, pct,
                          strategyWins[1], strategyWins[2], strategyWins[3]);
    }

    /** Detect strategy from agent name or participant id. Uses explicit map when available. */
    private int detectStrategy(String agentName, int participantId) {
        // First check explicit map
        Integer explicit = participantStrategy.get(participantId);
        if (explicit != null) return explicit;

        // Fallback to heuristic from agent name
        if (agentName == null) return 0;
        if (agentName.contains("strategy1")) return 1;
        if (agentName.contains("strategy2")) return 2;
        if (agentName.contains("strategy3")) return 3;
        // Heuristic: participant N maps based on ceil(m/3) boundaries
        // This is overridden by explicit map when strategyMap is provided
        return 3; // default
    }

    /** Legacy detection for calls that don't pass participantId */
    private int detectStrategy(String agentName) {
        return detectStrategy(agentName, -1);
    }

    private void writeReportToFile(String report) {
        try {
            String filename = "cnp_report_" +
                DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss")
                    .format(LocalDateTime.now()) + ".txt";
            try (PrintWriter pw = new PrintWriter(new FileWriter(filename))) {
                pw.println(report);
            }
            System.out.println("[MetricsBoard] Report saved to " + filename);
        } catch (IOException e) {
            System.err.println("[MetricsBoard] Failed to write report: " + e.getMessage());
        }
    }
}
