.subckt COMPLEX2 GND cl0#A cl1#A VCC cl0#Y cl1#S cl1#B
Mcl0#0 cl0#a_9_54# cl0#A VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#Y cl1#Y cl0#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#Y cl0#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 GND cl1#Y cl0#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 VCC cl1#S cl1#a_2_10# VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#a_17_50# cl1#B VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#2 cl1#Y cl1#S cl1#a_17_50# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#3 cl1#a_30_54# cl1#a_2_10# cl1#Y VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#4 VCC cl1#A cl1#a_30_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#5 GND cl1#S cl1#a_2_10# GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#6 cl1#a_17_10# cl1#B GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#7 cl1#Y cl1#a_2_10# cl1#a_17_10# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#8 cl1#a_30_10# cl1#S cl1#Y GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#9 GND cl1#A cl1#a_30_10# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX2
* pattern code: [NOR2X1,MUX2X1]
* 4311 occurrences in design 
* each contains 2 cells
* Example occurence:
*   .subckt NOR2X1 A=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[0] B=$abc$1084410$new_n293154_ Y=$abc$1084410$new_n293155_
*   .subckt MUX2X1 A=banked_predictors_0.components_1.tables_2.lo_us.hi_us_0_ext.mem_0_1.ram[206] B=banked_predictors_0.components_1.tables_2.lo_us.hi_us_0_ext.mem_0_1.ram[202] S=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[2] Y=$abc$1084410$new_n293154_
