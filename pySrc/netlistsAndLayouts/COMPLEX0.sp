.subckt COMPLEX0 cl2#A cl1#Y cl2#B GND cl0#A cl1#A cl2#C VCC cl0#Y
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
.ends COMPLEX0
* pattern code: [AOI21X1,INVX1,OAI21X1]
* 12970 occurrences in design 
* each contains 3 cells
* Example occurence:
*   .subckt AOI21X1 A=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[2] B=$abc$1084410$new_n266432_ C=$abc$1084410$new_n293156_ Y=$abc$1084410$new_n293157_
*   .subckt INVX1 A=banked_predictors_0.components_1.tables_2.lo_us.hi_us_0_ext.mem_0_1.ram[207] Y=$abc$1084410$new_n266432_
*   .subckt OAI21X1 A=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[2] B=banked_predictors_0.components_1.tables_2.lo_us.hi_us_0_ext.mem_0_1.ram[203] C=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[0] Y=$abc$1084410$new_n293156_
