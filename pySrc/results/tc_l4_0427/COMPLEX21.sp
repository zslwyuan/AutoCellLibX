.subckt COMPLEX21 cl2#C cl1#A cl0#A cl2#B VCC cl4#A cl2#A cl4#C GND cl3#B cl4#B cl3#Y
Mcl0#0 cl0#a_9_54# cl0#A VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#Y cl1#Y cl0#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 VCC cl2#Y cl0#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 GND cl0#A cl0#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#4 cl0#a_2_6# cl1#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#5 cl0#Y cl2#Y cl0#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#Y cl1#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#0 VCC cl2#A cl2#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 cl2#a_2_54# cl2#B VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 cl2#Y cl2#C cl2#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 cl2#a_12_6# cl2#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#4 cl2#Y cl2#B cl2#a_12_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#5 GND cl2#C cl2#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#0 cl3#Y cl0#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#1 VCC cl3#B cl3#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#2 cl3#Y cl4#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#3 cl3#a_9_6# cl0#Y GND GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#4 cl3#a_14_6# cl3#B cl3#a_9_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#5 cl3#Y cl4#Y cl3#a_14_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#0 cl4#Y cl4#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#1 VCC cl4#B cl4#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#2 cl4#Y cl4#C VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#3 cl4#a_9_6# cl4#A GND GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#4 cl4#a_14_6# cl4#B cl4#a_9_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#5 cl4#Y cl4#C cl4#a_14_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX21
* pattern code: [OAI21X1,INVX1,AOI21X1]+c0o0_NAND3X1+c3i1NAND3X1
* 86 occurrences in design 
* each contains 5 cells
* Example occurence:
*   .subckt OAI21X1 A=sel[0] B=w1_0781 C=w1_2358 Y=w1_5285
*   .subckt INVX1 A=din42[6] Y=w1_0781
*   .subckt AOI21X1 A=sel[0] B=din43[6] C=w1_4069 Y=w1_2358
*   .subckt NAND3X1 A=w1_5285 B=w1_3819 C=w1_3563 Y=w1_1610
*   .subckt NAND3X1 A=w1_2180 B=w1_3846 C=w1_4087 Y=w1_3563
