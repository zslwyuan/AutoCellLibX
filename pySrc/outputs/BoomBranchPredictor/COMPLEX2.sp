.subckt COMPLEX2 cl0#A cl2#A cl0#Y VCC cl1#Y cl2#B GND cl1#A cl2#C
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
.ends COMPLEX2
* pattern code: [AOI21X1,INVX1,OAI21X1]
* 14348 occurrences in design 
* each contains 3 cells
* Example occurence:
*   .subckt AOI21X1 A=$\components_1.tables_0.table_.table_ext.mem_0_0.ram$rdreg[0]$q[2] B=$abc$1080429$new_n266338_ C=$abc$1080429$new_n290293_ Y=$abc$1080429$new_n290294_
*   .subckt INVX1 A=components_1.tables_0.table_.table_ext.mem_0_0.ram[31][0] Y=$abc$1080429$new_n266338_
*   .subckt OAI21X1 A=$\components_1.tables_0.table_.table_ext.mem_0_0.ram$rdreg[0]$q[2] B=components_1.tables_0.table_.table_ext.mem_0_0.ram[27][0] C=$\components_1.tables_0.table_.table_ext.mem_0_0.ram$rdreg[0]$q[0] Y=$abc$1080429$new_n290293_
