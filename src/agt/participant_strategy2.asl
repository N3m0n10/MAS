// participant_strategy2.asl - Strategy 2: Adaptive Discount
// price = base_price - (rejected_count * discount)

strategy(adaptive_discount).
rejected_count(0).
contracts_won(0).
service_timeout_ms(200).

+cfp(ContractId, _InitId, service_request)[source(Initiator)]
    :  agent_id(MyId) & base_price(Base) & discount(D) & rejected_count(RC)
    <-  Deduction = RC * D;
        PriceRaw = Base - Deduction;
        if (PriceRaw > 0) {
            FinalPrice = PriceRaw
        } else {
            FinalPrice = 1
        };
        .print("[P-S2 ",MyId,"] CFP #",ContractId," from ",Initiator," proposing ",FinalPrice," (base=",Base,", rejected=",RC,", disc=",D,")");
        +pending_proposal(ContractId, Initiator, FinalPrice);
        .send(Initiator, tell, proposal(ContractId, FinalPrice)).

+award(ContractId, Value)[source(_Initiator)]
    :  agent_id(MyId) & contracts_won(W)
    <-  .print("[P-S2 ",MyId,"] WON contract #",ContractId," value=",Value);
        W2 = W + 1;
        -+contracts_won(W2);
        .abolish(pending_proposal(ContractId, _, _));
        ?service_timeout_ms(ST);
        .print("[P-S2 ",MyId,"] Performing service for #",ContractId," (",ST," ms).");
        .wait(ST);
participant_won(MyId, ContractId, Value, "strategy2").

+reject(ContractId)[source(_Initiator)]
    :  agent_id(MyId) & rejected_count(RC)
    <-  RC2 = RC + 1;
        .print("[P-S2 ",MyId,"] REJECTED on contract #",ContractId," (total=",RC2,")");
        -+rejected_count(RC2);
        .abolish(pending_proposal(ContractId, _, _));
participant_rejected(MyId, ContractId, "strategy2").

{ include("$jacamo/templates/common-cartago.asl") }
{ include("$jacamo/templates/common-moise.asl") }