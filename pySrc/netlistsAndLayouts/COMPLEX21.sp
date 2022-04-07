.subckt COMPLEX21 cl2#A GND cl0#A cl1#A cl2#C VCC cl1#S cl1#B cl2#Y
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
Mcl2#0 VCC cl2#A cl2#a_2_64# VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 cl2#a_2_64# cl2#A VCC VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 cl2#a_25_64# cl0#Y cl2#a_2_64# VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 cl2#a_2_64# cl0#Y cl2#a_25_64# VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#4 cl2#Y cl2#C cl2#a_25_64# VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#5 cl2#a_25_64# cl2#C cl2#Y VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#6 cl2#Y cl2#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#7 GND cl0#Y cl2#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#8 cl2#Y cl2#C GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX21
* pattern code: [NOR2X1,MUX2X1]+c0o0_NOR3X1
* 2853 occurrences in design 
* each contains 3 cells
* Example occurence:
*   .subckt NOR2X1 A=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[0] B=$abc$1084410$new_n293154_ Y=$abc$1084410$new_n293155_
*   .subckt MUX2X1 A=banked_predictors_0.components_1.tables_2.lo_us.hi_us_0_ext.mem_0_1.ram[206] B=banked_predictors_0.components_1.tables_2.lo_us.hi_us_0_ext.mem_0_1.ram[202] S=banked_predictors_0.components_1.tables_2.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[2] Y=$abc$1084410$new_n293154_
*   .subckt NOR3X1 A=$abc$1084410$new_n266395_ B=$abc$1084410$new_n293155_ C=$abc$1084410$new_n293157_ Y=$abc$1084410$new_n293158_
