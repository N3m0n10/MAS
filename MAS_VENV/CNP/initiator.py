from maspy import *


# NOTE: Considering necessity of full contract achieving --> loose tasks bid value
# talk with i participants per time


class basic_initiator(Agent):
    def __init__(self, name=None, wanted_value, min_value):
        super().__init__(name)
        self.add(Belief("wanted_value", wanted_value))
        self.add(Belief("min_value", min_value))
        self.add(Belief("start_cnp", True))

        """Ask participants if they want to propose. There isn't motivation for not accepting in this case, so I will add a small refuse prob"""
        @pl(gain, Goal("start_cnp", Any))
        def start_cnp(self, src):
            # ask one [random?] non closed participant for bid
            # n max parallel calls --> TODO
            self.send("random_participant", askOne, Belief("start_cnp"), "CNPChannel")
            pass
        
        """After cnp start, receive proposals and decide if accept or refuse"""
        @pl(gain, Goal("propose", Any))
        def propose(self, src, bid):
            # ask one [random?] non closed participant for bid
            # use propose_logic
            self.send("random_participant", askOne, Belief("contract",False), "CNPChannel")
            self.send("random_participant", askOne, Belief("contract",True), "CNPChannel")
            pass

        @pl(gain, Goal("contract", Any))
        def contract(self, src, contract):
            # end process
            pass