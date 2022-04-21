.subckt COMPLEX9 cl1#A VCC cl4#A cl1#B cl3#A cl4#B cl2#B cl0#Y cl4#C cl2#A cl1#C GND cl3#B
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
Mcl1#0 VCC cl1#A cl1#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#a_2_54# cl1#B VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#2 cl1#Y cl1#C cl1#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#3 cl1#a_12_6# cl1#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#4 cl1#Y cl1#B cl1#a_12_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#5 GND cl1#C cl1#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#0 cl2#Y cl2#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 VCC cl2#B cl2#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 cl2#a_9_6# cl2#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 cl2#Y cl2#B cl2#a_9_6# GND NMOS W=0.5u L=0.05u
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
.ends COMPLEX9
* pattern code: [AOI22X1,AOI21X1,NAND2X1,NAND2X1,AOI21X1]
* 86 occurrences in design 
* each contains 5 cells
* Example occurence:
*   .subckt AOI22X1 A=w1_4048 B=w1_4238 C=w1_0917 D=w1_0803 Y=w1_4552
*   .subckt AOI21X1 A=sel[0] B=din63[6] C=w1_3578 Y=w1_4048
*   .subckt NAND2X1 A=din62[6] B=w1_5249 Y=w1_4238
*   .subckt NAND2X1 A=sel[0] B=din55[6] Y=w1_0917
*   .subckt AOI21X1 A=w1_5249 B=din54[6] C=w1_1604 Y=w1_0803
