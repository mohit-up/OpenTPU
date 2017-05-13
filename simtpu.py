from pyrtl import *
import argparse
import numpy as np

#set_debug_mode()

from tpu import *
from config import INSTRUCTION_WIDTH

import sys

parser = argparse.ArgumentParser(description="Run the PyRTL spec for the TPU on the indicated program.")
parser.add_argument("prog", metavar="program.bin", help="A valid binary program for OpenTPU.")
parser.add_argument("hostmem", metavar="HostMemoryArray", help="A file containing a numpy array containing the initial contents of host memory. Each row represents one vector.")
parser.add_argument("weightsmem", metavar="WeightsMemoryArray", help="A file containing a numpy array containing the contents of the weights memroy. Each row represents one tile (the first row corresponds to the top row of the weights matrix).")

args = parser.parse_args()

# Read the program and build an instruction list
with open(args.prog, 'rb') as f:
    ins = [x for x in f.read()]  # create byte list from input

instrs = []
width = INSTRUCTION_WIDTH / 8
# This assumes instructions are strictly byte-aligned

for i in range(int(len(ins)/width)):  # once per instruction
    val = 0
    for j in range(int(width)):  # for each byte
        val = (val << 8) | ins.pop(0)
    instrs.append(val)

#print(list(map(hex, instrs)))

def concat_vec(vec, bits=8):
    t = 0
    mask = int('1'*bits, 2)
    for x in vec:
        t = (t<<bits) | (int(x) & mask)
    return t

def concat_tile(tile, bits=8):
    val = 0
    size = len(tile)
    mask = int('1'*bits, 2)
    for row in tile:
        for x in row:
            val = (val<<bits) | (int(x) & mask)
    #return val & (size*size*bits)  # if negative, truncate bits to correct size
    return val

def make_vec(value, bits=8):
    vec = []
    mask = int('1'*bits, 2)
    while value > 0:
        vec.append(value & mask)
        value = value >> 8
    return list(reversed(vec))

def print_mem(mem):
    ks = sorted(mem.keys())
    for a in ks:
        print(a, make_vec(mem[a]))

def print_weight_mem(mem, bits=8, size=8):
    ks = sorted(mem.keys())
    mask = int('1'*(size*bits), 2)
    vecs = []
    for a in ks:
        vec = []
        tile = mem[a]
        while tile > 0:
            vec.append(make_vec(tile & mask))
            tile = tile >> (8*8)
        vecs.append(vec)
    for a, vec in enumerate(vecs):
        print(a, list(reversed(vec)))
        
# Read the dram files and build memory images
hostarray = np.load(args.hostmem)
print(hostarray)
print(hostarray.shape)
hostmem = { a : concat_vec(vec) for a,vec in enumerate(hostarray) }
print("Host memory:")
print_mem(hostmem)
    

weightsarray = np.load(args.weightsmem)
print(weightsarray)
print(weightsarray.shape)
weightsmem = { a : concat_tile(tile) for a,tile in enumerate(weightsarray) }
#weightsmem = { a : concat_vec(vec) for a,vec in enumerate(weightsarray) }
print(weightsmem)
print("Weight memory:")
print_weight_mem(weightsmem)

'''
Left-most element of each vector should be left-most in memory: use concat_list for each vector

For weights mem, first vector goes last; hardware already handles this by iterating from back to front over the tile.
The first vector should be at the "front" of the tile.

For host mem, each vector goes at one address. First vector at address 0.
'''

# Run Simulation
sim_trace = SimulationTrace()
sim = FastSimulation(tracer=sim_trace, memory_value_map={ IMem : { a : v for a,v in enumerate(instrs)} })

windex = 0
d = {
    weights_in : weightsmem[windex],
    hostmem_rdata : 0,
}

sim.step(d)
i = 0
while True:
    i += 1
    # Halt signal
    if sim.inspect(halt):
        break

    # Read weights signal
    if sim.inspect(read_weights):
        windex += 1
        if windex <= max(weightsmem.keys()):
            # If we have another weight tile in memory, use it
            d[weights_in] = weightsmem[windex]

    # Read host memory signal
    if sim.inspect(hostmem_re):
        raddr = sim.inspect(hostmem_raddr)
        if raddr in hostmem:
            d[hostmem_rdata] = hostmem[raddr]

    # Write host memory signal
    if sim.inspect(hostmem_we):
        waddr = sim.inspect(hostmem_waddr)
        wdata = sim.inspect(hostmem_wdata)
        hostmem[waddr] = wdata
            
    sim.step(d)

print("Host memory:")
print_mem(hostmem)

#sim_trace.render_trace()
with open("trace.vcd", 'w') as f:
    sim_trace.print_vcd(f)
