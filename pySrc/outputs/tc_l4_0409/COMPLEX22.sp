.subckt COMPLEX22 cl2#C cl5#A cl1#A cl1#B cl2#B VCC cl4#A cl2#A cl4#C GND cl3#A cl3#B cl4#B cl5#Y cl5#C
Mcl0#0 VCC cl1#Y cl0#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#a_2_54# cl2#Y VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#Y cl4#Y cl0#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#a_2_54# cl3#Y cl0#Y VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#4 cl0#a_11_6# cl1#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#5 cl0#Y cl2#Y cl0#a_11_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#6 cl0#a_28_6# cl4#Y cl0#Y GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#7 GND cl3#Y cl0#a_28_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 VCC cl1#B cl1#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#2 cl1#a_9_6# cl1#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#3 cl1#Y cl1#B cl1#a_9_6# GND NMOS W=0.5u L=0.05u
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
Mcl3#0 cl3#Y cl3#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#1 VCC cl3#B cl3#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#2 cl3#a_9_6# cl3#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#3 cl3#Y cl3#B cl3#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#0 VCC cl4#A cl4#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#1 cl4#a_2_54# cl4#B VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#2 cl4#Y cl4#C cl4#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#3 cl4#a_12_6# cl4#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#4 cl4#Y cl4#B cl4#a_12_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#5 GND cl4#C cl4#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl5#0 cl5#Y cl5#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl5#1 VCC cl0#Y cl5#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl5#2 cl5#Y cl5#C VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl5#3 cl5#a_9_6# cl5#A GND GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl5#4 cl5#a_14_6# cl0#Y cl5#a_9_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl5#5 cl5#Y cl5#C cl5#a_14_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX22
* pattern code: [AOI22X1,NAND2X1,AOI21X1,NAND2X1,AOI21X1]+c0o0_NAND3X1
* 77 occurrences in design 
* each contains 6 cells
* Example occurence:
*   .subckt AOI22X1 A=w1_0697 B=w1_1332 C=w1_2798 D=w1_0377 Y=w1_0646
*   .subckt NAND2X1 A=sel[0] B=din1[13] Y=w1_0697
*   .subckt AOI21X1 A=w1_4044 B=din0[13] C=w1_3537 Y=w1_1332
*   .subckt NAND2X1 A=sel[0] B=din13[13] Y=w1_2798
*   .subckt AOI21X1 A=w1_4044 B=din12[13] C=w1_0522 Y=w1_0377
*   .subckt NAND3X1 A=w1_2596 B=w1_0646 C=w1_3584 Y=w1_4030
