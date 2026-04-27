// initiator.asl - Contract Net Protocol - Initiator role

timeout_ms(3000).
service_receive_timeout_ms(200).
available.
remaining_contracts(0).

// Threshold for proposal acceptance (set by generator, default 200)
price_threshold(200).

!start.

+!start : agent_id(Id) & num_contracts(NC) & num_participants(NP)
    <-  -+remaining_contracts(NC);
        .print("[Initiator ",Id,"] Starting ",NC," parallel CNPs with ",NP," participants.");
        !launch_contracts(1, NC, Id, NP).

+!launch_contracts(I, Max, AgId, NP) : I > Max
    <-  true.

+!launch_contracts(I, Max, AgId, NP) : I <= Max
    <-  ContractId = AgId * 1000 + I;
        !!run_cnp(ContractId, AgId, NP);
        I2 = I + 1;
        !launch_contracts(I2, Max, AgId, NP).

+!run_cnp(ContractId, AgId, NP) : available
    <-  ?price_threshold(Thresh);
        .print("[Initiator ",AgId,"] CFP #",ContractId," broadcasting to ",NP," participants, threshold=",Thresh);
        !broadcast_cfp(ContractId, AgId, 1, NP);
        ?timeout_ms(Timeout);
        .wait(Timeout);
        !evaluate_proposals(ContractId, AgId, Thresh).

+!broadcast_cfp(CId, AgId, K, NP) : K > NP
    <-  true.

+!broadcast_cfp(CId, AgId, K, NP) : K <= NP
    <-  .concat("participant", K, PName);
        .send(PName, tell, cfp(CId, AgId, service_request));
        K2 = K + 1;
        !broadcast_cfp(CId, AgId, K2, NP).

+!evaluate_proposals(ContractId, AgId, T)
    <-  .findall(bid(Val, Sender), proposal(ContractId, Val)[source(Sender)], Proposals);
        .length(Proposals, NProp);
        .print("[Initiator ",AgId,"] Contract #",ContractId," received ",NProp," proposal(s).");
        // Record proposal count to MetricsBoard via artifact operation
        record_proposal_count(ContractId, AgId, NProp);
        !select_winner(ContractId, AgId, Proposals, T).

+!select_winner(ContractId, AgId, [], T)
    <-  .print("[Initiator ",AgId,"] Contract #",ContractId," FAILED - no proposals.");
        failed_contract(ContractId, AgId);
        !contract_finished(ContractId, AgId, 0).

+!select_winner(ContractId, AgId, Proposals, T) : Proposals \== []
    <-  !filter_by_threshold(Proposals, T, Below, Above);
        .length(Above, NAbove);
        .print("[Initiator ",AgId,"] Contract #",ContractId," filtered ",NAbove," proposal(s) above threshold ",T);
        !record_threshold_rejections(ContractId, AgId, Above);
        !split_lowest_k(Below, 10, Winners, Losers);
        .length(Winners, NWinners);
        .print("[Initiator ",AgId,"] Contract #",ContractId," awarding ",NWinners," proposal(s) among ",NWinners,"+",NAbove," total rejected.");
        !send_awards(ContractId, Winners, AgId);
        !send_rejections_threshold(ContractId, Above);
        !send_rejections(ContractId, Losers);
        !retract_proposals(ContractId);
        ?service_receive_timeout_ms(ST);
        .wait(ST);
        !contract_finished(ContractId, AgId, NWinners).

+!filter_by_threshold([bid(V, S)|Rest], T, Below, Above)
    <-  if (V > T) {
            !filter_by_threshold(Rest, T, Below, Above2);
            .concat([bid(V, S)], Above2, Above)
        } else {
            !filter_by_threshold(Rest, T, Below2, Above);
            .concat([bid(V, S)], Below2, Below)
        }.

+!filter_by_threshold([], _, [], []).

+!split_lowest_k([], _, [], []) <- true.

// Base case: empty list with K>0 (no winners possible)
+!split_lowest_k([], K, [], []) : K > 0 <- true.

// Recursive case: pick minimum and continue
+!split_lowest_k(Proposals, K, [bid(MinV, MinS)|Winners], Losers)
    : K > 0 & Proposals \== []
    <-  !pick_min(Proposals, MinV, MinS, Remaining);
        K2 = K - 1;
        !split_lowest_k(Remaining, K2, Winners, Losers).

+!pick_min([bid(V, S)|Rest], MinV, MinS, Remaining)
    <-  !pick_min_acc(Rest, V, S, [], MinV, MinS, Remaining).

+!pick_min_acc([], CurMinV, CurMinS, Acc, CurMinV, CurMinS, Acc).

+!pick_min_acc([bid(V, S)|Rest], CurMinV, CurMinS, Acc, MinV, MinS, Remaining) : V < CurMinV
    <-  !pick_min_acc(Rest, V, S, [bid(CurMinV, CurMinS)|Acc], MinV, MinS, Remaining).

+!pick_min_acc([bid(V, S)|Rest], CurMinV, CurMinS, Acc, MinV, MinS, Remaining) : V >= CurMinV
    <-  !pick_min_acc(Rest, CurMinV, CurMinS, [bid(V, S)|Acc], MinV, MinS, Remaining).

+!send_awards(_, [], _).

+!send_awards(ContractId, [bid(V, S)|Rest], AgId)
    <-  .send(S, tell, award(ContractId, V));
        awarded_contract(ContractId, AgId, S, V);
        record_winning_price(ContractId, S, V);
        !send_awards(ContractId, Rest, AgId).

+!send_rejections_threshold(_, []).

+!send_rejections_threshold(ContractId, [bid(V, S)|Rest])
    <-  .send(S, tell, reject(ContractId));
        !send_rejections_threshold(ContractId, Rest).

+!send_rejections(_, []).

+!send_rejections(ContractId, [bid(_V, S)|Rest])
    <-  .send(S, tell, reject(ContractId));
        !send_rejections(ContractId, Rest).

+!retract_proposals(ContractId)
    <-  .abolish(proposal(ContractId, _)).

+!record_threshold_rejections(_, _, []).
+!record_threshold_rejections(ContractId, AgId, [bid(V, S)|Rest])
    <-  record_threshold_rejection(ContractId, AgId, V);
        !record_threshold_rejections(ContractId, AgId, Rest).

+!contract_finished(ContractId, AgId, AwardCount)
    : remaining_contracts(R) & R > 0
    <-  R2 = R - 1;
        -+remaining_contracts(R2);
        .print("[Initiator ",AgId,"] Contract #",ContractId," closed with ",AwardCount," award(s). Remaining=",R2);
        if (R2 == 0) {
            -available;
            +unavailable;
            .print("[Initiator ",AgId,"] Service batch complete. Initiator unavailable.")
        }.

+!contract_finished(ContractId, AgId, AwardCount)
    : remaining_contracts(0)
    <-  .print("[Initiator ",AgId,"] All contracts completed.").

{ include("$jacamo/templates/common-cartago.asl") }
{ include("$jacamo/templates/common-moise.asl") }