import os

verilog_list = ["./boomModule/v_files/*.v"]  # "./gemmini/*.v"]
# verilog_list = ["./EPFL/arithmetic/log2/verilog/log2.v",
#                "./EPFL/arithmetic/sqrt/verilog/sqrt.v",
#                "./EPFL/arithmetic/hypotenuse/verilog/hyp.v",
#                "./EPFL/arithmetic/bar/verilog/bar.v",
#                "./EPFL/arithmetic/multiplier/verilog/multiplier.v",
#                "./EPFL/arithmetic/max/verilog/max.v",
#                "./EPFL/arithmetic/sin/verilog/sin.v",
#                "./EPFL/arithmetic/square/verilog/square.v",
#                "./EPFL/arithmetic/divisor/verilog/div.v",
#                "./EPFL/arithmetic/adder/verilog/adder.v",
#                "./EPFL/random_control/i2c/verilog/i2c.v",
#                "./EPFL/random_control/int2float/verilog/int2float.v",
#                "./EPFL/random_control/priority/verilog/priority.v",
#                "./EPFL/random_control/alu_ctrl/verilog/ctrl.v",
#                "./EPFL/random_control/round_robin_arbiter/verilog/arbiter.v",
#                "./EPFL/random_control/mem_ctrl/verilog/mem_ctrl.v",
#                "./EPFL/random_control/voter/verilog/voter.v",
#                "./EPFL/random_control/cavlc/verilog/cavlc.v",
#                "./EPFL/random_control/decoder/verilog/dec.v",
#                "./EPFL/random_control/router/verilog/router.v"]

# syn_template = """
# read_liberty -lib ../stdCelllib/gscl45nm.lib
# read -sv TARGETVERILOG
# hierarchy -top top
# flatten
# synth -top top
# flatten

# # the high-level stuff
# proc; fsm; opt; memory; opt

# # mapping flip-flops to mycells.lib
# dfflibmap -liberty ../stdCelllib/gscl45nm.lib

# # mapping logic to mycells.lib
# abc  -liberty ../stdCelllib/gscl45nm.lib
# opt
# opt
# clean
# opt
# clean

# write_blif OUTPUTPATH/BENCHMARKNAME.blif
# """

syn_template = """
read_liberty -lib ../stdCelllib/gscl45nm.lib
read -sv TARGETVERILOG
hierarchy -top RegisterFileSynthesizable
flatten
synth -top RegisterFileSynthesizable
flatten

# the high-level stuff
proc; fsm; opt; memory; opt

# mapping flip-flops to mycells.lib
dfflibmap -liberty ../stdCelllib/gscl45nm.lib

# mapping logic to mycells.lib
abc  -liberty ../stdCelllib/gscl45nm.lib
opt
opt
clean
opt
clean

write_blif OUTPUTPATH/BoomRegisterFile.blif
"""


output_path = "/home/zslwyuan-laptop/Softwares/yosys/blifPatternExtraction_Jingsong/benchmark/blif/"
yosys_path = "/home/zslwyuan-laptop/Softwares/yosys/yosys"

for target_verilog in verilog_list:
    benchmark_name = target_verilog.split("/")[-1].split(".")[0]
    output_str = syn_template.replace(
        "BENCHMARKNAME", benchmark_name).replace("OUTPUTPATH", output_path).replace("TARGETVERILOG", target_verilog)
    syn_script = open("syn.ys", 'w')
    print(output_str, file=syn_script)
    syn_script.close()
    os.system(yosys_path+" syn.ys")
