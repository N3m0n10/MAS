# wait for request
# receive request 
# analise val
# accept or refuse or propose
# wait for response
# reject or accept (1 proposal only)
# inform 

# NOTE: things to ponder: agent knowleged of remaining contractors and finished participants --> inflaction value, agressive bid
# Analyse total contract value, not used agents (if any)
# Averege value variation from initial bid
from maspy import *


class basic_participant(Agent):
    def __init__(self, name=None, wanted_value, min_value):
        super().__init__(name)
        self.add(Belief("wanted_value", wanted_value))
        self.add(Belief("min_value", min_value))
        self.timeout = 10000

        """After receiving "start_cnp", send a propose or cut connection"""
        @pl(gain, Goal("start_cnp", Any))
        def receive_request(self, src):
            # propose bid
            send(src, propose, Belief("propose", self.propose_logic()), "CNPChannel")
            pass

        """After receiving the contract, inform or cancel [will not cancel for simplicity]. 
        The agent will close after accepting, and wait for next cnp if not called by all initiators already"""
        @pl(gain, Belief("contract", Any))
        def receive_propose(self, src, propose):
            # accept or refuse or propose better bid
            pass
        
        def propose_logic(self):
            # logic to decide if accept, refuse or propose better bid
            pass

class risky_participant(basic_participant):
    def __init__(self, name=None, wanted_value, min_value):
        super().__init__(name, wanted_value, min_value)
        
    def propose_logic(self):
        # more agressive logic to decide if accept, refuse or propose better bid
        pass