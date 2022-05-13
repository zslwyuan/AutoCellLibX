.subckt COMPLEX4 cl1#Y cl1#C cl2#B cl1#A cl1#B cl2#Y cl3#A cl0#Y GND VCC cl2#A cl3#B cl3#C
Mcl0#0 VCC cl1#Y cl0#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#a_2_54# cl2#Y VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#Y cl3#Y cl0#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#a_12_6# cl1#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#4 cl0#Y cl2#Y cl0#a_12_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#5 GND cl3#Y cl0#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#a_9_54# cl1#A VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#Y cl1#B cl1#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#2 VCC cl1#C cl1#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#3 GND cl1#A cl1#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#4 cl1#a_2_6# cl1#B GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#5 cl1#Y cl1#C cl1#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#0 VCC cl2#A cl2#a_2_6# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 cl2#a_18_54# cl2#a_12_41# VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 cl2#Y cl2#a_2_6# cl2#a_18_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 cl2#a_35_54# cl2#A cl2#Y VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#4 VCC cl2#B cl2#a_35_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#5 cl2#a_12_41# cl2#B VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#6 GND cl2#A cl2#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#7 cl2#a_18_6# cl2#a_12_41# GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#8 cl2#Y cl2#A cl2#a_18_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#9 cl2#a_35_6# cl2#a_2_6# cl2#Y GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#10 GND cl2#B cl2#a_35_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#11 cl2#a_12_41# cl2#B GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#0 VCC cl3#A cl3#a_2_64# VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#1 cl3#a_2_64# cl3#A VCC VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#2 cl3#a_25_64# cl3#B cl3#a_2_64# VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#3 cl3#a_2_64# cl3#B cl3#a_25_64# VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#4 cl3#Y cl3#C cl3#a_25_64# VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#5 cl3#a_25_64# cl3#C cl3#Y VCC PMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#6 cl3#Y cl3#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#7 GND cl3#B cl3#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#8 cl3#Y cl3#C GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX4
* pattern code: [AOI21X1,OAI21X1,XNOR2X1,NOR3X1]
* 94 occurrences in design 
* each contains 4 cells
* Example occurence:
*   .subckt AOI21X1 A=$abc$122999$new_n1246_ B=$abc$122999$new_n1249_ C=$abc$122999$new_n1244_ Y=$abc$122999$new_n1250_
*   .subckt OAI21X1 A=$abc$122999$new_n1239_ B=$abc$122999$new_n1242_ C=$abc$122999$new_n339_ Y=$abc$122999$new_n1246_
*   .subckt XNOR2X1 A=$abc$122999$new_n1136_ B=$abc$122999$new_n1248_ Y=$abc$122999$new_n1249_
*   .subckt NOR3X1 A=$abc$122999$new_n339_ B=$abc$122999$new_n1239_ C=$abc$122999$new_n1242_ Y=$abc$122999$new_n1244_
