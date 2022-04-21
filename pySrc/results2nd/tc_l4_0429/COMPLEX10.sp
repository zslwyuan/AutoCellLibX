.subckt COMPLEX10 GND cl0#Y cl2#B VCC cl1#A cl1#C cl2#C cl3#B cl3#C cl2#A cl1#B cl3#A
Mcl0#0 cl0#Y cl1#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 VCC cl2#Y cl0#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#Y cl3#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#a_9_6# cl1#Y GND GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#4 cl0#a_14_6# cl2#Y cl0#a_9_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#5 cl0#Y cl3#Y cl0#a_14_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 VCC cl1#B cl1#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#2 cl1#Y cl1#C VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#3 cl1#a_9_6# cl1#A GND GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#4 cl1#a_14_6# cl1#B cl1#a_9_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#5 cl1#Y cl1#C cl1#a_14_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#0 cl2#Y cl2#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 VCC cl2#B cl2#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 cl2#Y cl2#C VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 cl2#a_9_6# cl2#A GND GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#4 cl2#a_14_6# cl2#B cl2#a_9_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#5 cl2#Y cl2#C cl2#a_14_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#0 cl3#Y cl3#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#1 VCC cl3#B cl3#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#2 cl3#Y cl3#C VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#3 cl3#a_9_6# cl3#A GND GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#4 cl3#a_14_6# cl3#B cl3#a_9_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#5 cl3#Y cl3#C cl3#a_14_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX10
* pattern code: [NAND3X1,NAND3X1,NAND3X1,NAND3X1]
* 89 occurrences in design 
* each contains 4 cells
* Example occurence:
*   .subckt NAND3X1 A=w1_1769 B=w1_1773 C=w1_3652 Y=w1_0192
*   .subckt NAND3X1 A=w1_0198 B=w1_3697 C=w1_3784 Y=w1_1769
*   .subckt NAND3X1 A=w1_0211 B=w1_0821 C=w1_4296 Y=w1_1773
*   .subckt NAND3X1 A=w1_1783 B=w1_1787 C=w1_4354 Y=w1_3652
