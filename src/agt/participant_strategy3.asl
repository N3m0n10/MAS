// participant_strategy3.asl - Strategy 3: Fixed Price
// Always proposes fixed_price regardless of history.

strategy(fixed_price).
contracts_won(0).
contracts_rejected(0).
service_timeout_ms(200).

+cfp(ContractId, _InitId, service_request)[source(Initiator)]
    :  agent_id(MyId) & fixed_price(Price)
    <-  .print("[P-S3 ",MyId,"] CFP #",ContractId," from ",Initiator," proposing fixed ",Price);
        +pending_proposal(ContractId, Initiator, Price);
        .send(Initiator, tell, proposal(ContractId, Price)).

+award(ContractId, Value)[source(_Initiator)]
    :  agent_id(MyId) & contracts_won(W)
    <-  .print("[P-S3 ",MyId,"] WON contract #",ContractId," value=",Value);
        W2 = W + 1;
        -+contracts_won(W2);
        .abolish(pending_proposal(ContractId, _, _));
        ?service_timeout_ms(ST);
        .print("[P-S3 ",MyId,"] Performing service for #",ContractId," (",ST," ms).");
        .wait(ST);
participant_won(MyId, ContractId, Value, "strategy3").

+reject(ContractId)[source(_Initiator)]
    :  agent_id(MyId) & contracts_rejected(R)
    <-  .print("[P-S3 ",MyId,"] REJECTED on contract #",ContractId);
        R2 = R + 1;
        -+contracts_rejected(R2);
        .abolish(pending_proposal(ContractId, _, _));
participant_rejected(MyId, ContractId, "strategy3").

{ include("$jacamo/templates/common-cartago.asl") }
{ include("$jacamo/templates/common-moise.asl") }