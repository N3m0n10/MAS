// participant_strategy1.asl - Strategy 1: Random Price Variation
// price = base_price + random(-20%, +20%)

strategy(random_variation).
contracts_won(0).
contracts_rejected(0).
service_timeout_ms(200).

+cfp(ContractId, _InitId, service_request)[source(Initiator)]
    :  agent_id(MyId) & base_price(Base)
    <-  Range = (Base * 20) div 100;
        .random(R);
        VarFloat = R * 2.0 * Range - Range;
        Variation = math.round(VarFloat);
        PriceRaw = Base + Variation;
        .print("[P-S1 ",MyId,"] CFP #",ContractId," proposing raw=",PriceRaw);
        if (PriceRaw > 0) {
            FinalPrice = PriceRaw
        } else {
            FinalPrice = 1
        };
        .print("[P-S1 ",MyId,"] CFP #",ContractId," from ",Initiator," proposing ",FinalPrice);
        +pending_proposal(ContractId, Initiator, FinalPrice);
        .send(Initiator, tell, proposal(ContractId, FinalPrice)).

+award(ContractId, Value)[source(_Initiator)]
    :  agent_id(MyId) & contracts_won(W)
    <-  .print("[P-S1 ",MyId,"] WON contract #",ContractId," value=",Value);
        W2 = W + 1;
        -+contracts_won(W2);
        .abolish(pending_proposal(ContractId, _, _));
        ?service_timeout_ms(ST);
        .print("[P-S1 ",MyId,"] Performing service for #",ContractId," (",ST," ms).");
        .wait(ST);
participant_won(MyId, ContractId, Value, "strategy1").

+reject(ContractId)[source(_Initiator)]
    :  agent_id(MyId) & contracts_rejected(R)
    <-  .print("[P-S1 ",MyId,"] REJECTED on contract #",ContractId);
        R2 = R + 1;
        -+contracts_rejected(R2);
        .abolish(pending_proposal(ContractId, _, _));
participant_rejected(MyId, ContractId, "strategy1").

{ include("$jacamo/templates/common-cartago.asl") }
{ include("$jacamo/templates/common-moise.asl") }