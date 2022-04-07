.subckt COMPLEX16 cl3#S cl2#A GND cl4#B cl2#C cl3#B cl1#A cl4#A cl2#B cl4#Y cl0#A cl3#Y VCC
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
Mcl4#0 VCC cl4#A cl4#a_2_64# VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#1 cl4#a_2_64# cl4#A VCC VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#2 cl4#a_25_64# cl4#B cl4#a_2_64# VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#3 cl4#a_2_64# cl4#B cl4#a_25_64# VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#4 cl4#Y cl0#Y cl4#a_25_64# VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#5 cl4#a_25_64# cl0#Y cl4#Y VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#6 cl4#Y cl4#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#7 GND cl4#B cl4#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#8 cl4#Y cl0#Y GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX16
* pattern code: [AOI21X1,INVX1,OAI21X1]+c1o0_MUX2X1+c0o0_NOR3X1
* 3275 occurrences in design 
* each contains 5 cells
* Example occurence:
*   .subckt AOI21X1 A=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[2] B=$abc$1084410$new_n266432_ C=$abc$1084410$new_n293156_ Y=$abc$1084410$new_n293157_
*   .subckt INVX1 A=banked_predictors_0.components_1.tables_2.lo_us.hi_us_0_ext.mem_0_1.ram[207] Y=$abc$1084410$new_n266432_
*   .subckt OAI21X1 A=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[2] B=banked_predictors_0.components_1.tables_2.lo_us.hi_us_0_ext.mem_0_1.ram[203] C=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[0] Y=$abc$1084410$new_n293156_
*   .subckt MUX2X1 A=$abc$1084410$new_n266432_ B=$abc$1084410$new_n492667_ S=$abc$1084410$new_n540053_ Y=$abc$1084410$auto$rtlil.cc:2551:MuxGate$865171
*   .subckt NOR3X1 A=$abc$1084410$new_n266395_ B=$abc$1084410$new_n293155_ C=$abc$1084410$new_n293157_ Y=$abc$1084410$new_n293158_
