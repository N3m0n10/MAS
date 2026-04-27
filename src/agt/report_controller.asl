// report_controller.asl - Triggers final metrics report and prints summary
// This agent waits for all initiators to finish, then requests the final report.

!start.

+!start
    <-  !wait_for_completion.

+!wait_for_completion
    <-  .print("[ReportController] Waiting for all initiators to complete...");
        ?num_initiators(N);
        ?total_contracts(TC);
        .print("[ReportController] n=",N," initiators, ",TC," total contracts.");
        .wait(30000);
        !print_final_report.

+!print_final_report
    <-  .print("[ReportController] Requesting final metrics report...");
        print_report();
        .print("[ReportController] Report generation requested.").

{ include("$jacamo/templates/common-cartago.asl") }
{ include("$jacamo/templates/common-moise.asl") }