from maspy import *
import random as rnd


"""
agent = DummyAgent("Ag")
agent.add( Goal(Name, Values, Source) )
agent.rm( Goal(Name, Values, Source) )
        
agent.add( Goal("check_house", {"Area": [50,100], "Rooms": 5}, ("Seller",27) ) )
agent.add( Goal("SendInfo", ("Information",["List","of","Information",42]) ) )
agent.rm( Goal("walk", source=("trainer",2)) )
"""

"""
self.send(<target>, <directive>, <info>, optional[<channel>])

Directives:
tell 		-> Add Belief on target
untell		-> Remove Belief from target
achieve 	-> Add Goal to target
unachieve	-> Remove Goal from target
askOne		-> Ask for Belief from target
askOneReply	-> Ask for Belief from target and wait for Reply
askAll		-> Ask for all similar Beliefs from target
askAllReply	-> Ask for all similar Beliefs from target and wait for Reply
tellHow		-> Add Plan on target
untellHow	-> Remove Plan from target
askHow 		-> Ask for Plan from target
askHowReply	-> Ask for Plan from target and wait for Reply
"""

class SimpleEnv(Environment):
    def env_act(self, agt, agent2):
        self.print(f"Contact between {agt} and {agent2}")

class SimpleAgent(Agent):
    @pl(gain,Goal("say_hello", Any))
    def send_hello(self,src,agent):
        self.send(agent,tell,Belief("Hello"),"SimpleChannel")

    @pl(gain,Belief("Hello"))
    def recieve_hello(self,src):
        self.print(f"Hello received from {src}")
        self.env_act(src)

if __name__ == "__main__":
    #Admin().set_logging(show_exec=True)
    agent1 = SimpleAgent()
    agent2 = SimpleAgent()
    env = SimpleEnv()
    ch = Channel("SimpleChannel")
    Admin().connect_to([agent1,agent2],[env,ch])
    agent1.add(Goal("say_hello",(agent2.my_name,)))
    Admin().start_system()