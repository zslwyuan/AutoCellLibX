.subckt COMPLEX1 cl0#Y GND cl2#B cl1#A cl1#C cl3#B cl4#Y cl4#A cl4#C VCC cl1#D cl2#A cl1#B cl3#A
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
Mcl1#0 VCC cl1#A cl1#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#a_2_54# cl1#B VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#2 cl1#Y cl1#D cl1#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#3 cl1#a_2_54# cl1#C cl1#Y VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#4 cl1#a_11_6# cl1#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#5 cl1#Y cl1#B cl1#a_11_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#6 cl1#a_28_6# cl1#D cl1#Y GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#7 GND cl1#C cl1#a_28_6# GND NMOS W=0.5u L=0.05u
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
Mcl4#0 cl4#a_9_54# cl4#A VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#1 cl4#Y cl0#Y cl4#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#2 VCC cl4#C cl4#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#3 GND cl4#A cl4#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#4 cl4#a_2_6# cl0#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#5 cl4#Y cl4#C cl4#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX1
* pattern code: [NAND3X1,AOI22X1,NAND2X1,NAND2X1]+c0o0_OAI21X1
* 83 occurrences in design 
* each contains 5 cells
* Example occurence:
*   .subckt NAND3X1 A=w1_0792 B=w1_0786 C=w1_0790 Y=w1_0795
*   .subckt AOI22X1 A=w1_0374 B=w1_0430 C=w1_0412 D=w1_1861 Y=w1_0792
*   .subckt NAND2X1 A=w1_2016 B=w1_0617 Y=w1_0786
*   .subckt NAND2X1 A=w1_2017 B=w1_0616 Y=w1_0790
*   .subckt OAI21X1 A=w1_0794 B=w1_0795 C=w1_0668 Y=w1_1502
