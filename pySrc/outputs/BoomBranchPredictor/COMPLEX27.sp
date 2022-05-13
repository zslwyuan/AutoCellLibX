.subckt COMPLEX27 cl0#A cl2#A cl0#Y VCC cl3#Y cl3#S cl2#B GND cl3#B cl1#A cl2#C
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
.ends COMPLEX27
* pattern code: [AOI21X1,INVX1,OAI21X1]+MUX2X1_c1o0
* 13552 occurrences in design 
* each contains 4 cells
* Example occurence:
*   .subckt AOI21X1 A=$\components_1.tables_0.table_.table_ext.mem_0_0.ram$rdreg[0]$q[2] B=$abc$1080429$new_n266338_ C=$abc$1080429$new_n290293_ Y=$abc$1080429$new_n290294_
*   .subckt INVX1 A=components_1.tables_0.table_.table_ext.mem_0_0.ram[31][0] Y=$abc$1080429$new_n266338_
*   .subckt OAI21X1 A=$\components_1.tables_0.table_.table_ext.mem_0_0.ram$rdreg[0]$q[2] B=components_1.tables_0.table_.table_ext.mem_0_0.ram[27][0] C=$\components_1.tables_0.table_.table_ext.mem_0_0.ram$rdreg[0]$q[0] Y=$abc$1080429$new_n290293_
*   .subckt MUX2X1 A=$abc$1080429$new_n266338_ B=$abc$1080429$new_n493273_ S=$abc$1080429$new_n551146_ Y=$abc$1080429$auto$rtlil.cc:2551:MuxGate$875446
