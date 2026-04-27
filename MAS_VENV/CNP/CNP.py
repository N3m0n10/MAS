"""Main file"""
from maspy import * 
from initiator import *
from participant import *
import random as rnd



# inside class, or env... [see later]
parts_num = 200
initiator_num = 50
parts = {i: basic_participant(name=f"part_{i}", wanted_value=rnd.randint(14,25), min_value=rnd.randint(8,13)) for i in range(parts_num)}