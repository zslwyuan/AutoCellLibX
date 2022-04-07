.subckt COMPLEX24 cl3#S cl2#A cl2#B cl4#Y GND cl0#A cl1#A cl4#B cl2#C cl3#B cl3#Y VCC
Mcl0#0 VCC cl0#A cl0#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#a_2_54# cl1#Y VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#Y cl2#Y cl0#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#a_12_6# cl0#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#4 cl0#Y cl1#Y cl0#a_12_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#5 GND cl2#Y cl0#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#Y cl1#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#0 cl2#a_9_54# cl2#A VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 cl2#Y cl2#B cl2#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 VCC cl2#C cl2#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 GND cl2#A cl2#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#4 cl2#a_2_6# cl2#B GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#5 cl2#Y cl2#C cl2#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#0 VCC cl3#S cl3#a_2_10# VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#1 cl3#a_17_50# cl3#B VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#2 cl3#Y cl3#S cl3#a_17_50# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#3 cl3#a_30_54# cl3#a_2_10# cl3#Y VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#4 VCC cl1#Y cl3#a_30_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#5 GND cl3#S cl3#a_2_10# GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#6 cl3#a_17_10# cl3#B GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#7 cl3#Y cl3#a_2_10# cl3#a_17_10# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#8 cl3#a_30_10# cl3#S cl3#Y GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#9 GND cl1#Y cl3#a_30_10# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#0 cl4#a_9_54# cl0#Y cl4#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#1 VCC cl4#B cl4#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#2 cl4#Y cl4#a_2_54# VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#3 cl4#a_2_54# cl0#Y GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#4 GND cl4#B cl4#a_2_54# GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#5 cl4#Y cl4#a_2_54# GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX24
* pattern code: [AOI21X1,INVX1,OAI21X1]+c1o0_MUX2X1+c0o0_OR2X1
* 1733 occurrences in design 
* each contains 5 cells
* Example occurence:
*   .subckt AOI21X1 A=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[2] B=$abc$1084410$new_n266415_ C=$abc$1084410$new_n293422_ Y=$abc$1084410$new_n293423_
*   .subckt INVX1 A=banked_predictors_0.components_1.tables_2.lo_us.hi_us_0_ext.mem_0_1.ram[103] Y=$abc$1084410$new_n266415_
*   .subckt OAI21X1 A=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[2] B=banked_predictors_0.components_1.tables_2.lo_us.hi_us_0_ext.mem_0_1.ram[99] C=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[0] Y=$abc$1084410$new_n293422_
*   .subckt MUX2X1 A=$abc$1084410$new_n266415_ B=$abc$1084410$new_n492667_ S=$abc$1084410$new_n540466_ Y=$abc$1084410$auto$rtlil.cc:2551:MuxGate$865379
*   .subckt OR2X1 A=$abc$1084410$new_n293423_ B=$abc$1084410$new_n293425_ Y=$abc$1084410$new_n293426_
