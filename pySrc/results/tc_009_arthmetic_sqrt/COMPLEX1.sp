.subckt COMPLEX1 VCC cl1#Y GND cl1#A cl1#B cl0#Y
Mcl0#0 cl0#Y cl1#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#Y cl1#Y GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#a_2_6# cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 VCC cl1#B cl1#a_2_6# VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#2 cl1#Y cl1#a_2_6# VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#3 cl1#a_9_6# cl1#A cl1#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#4 GND cl1#B cl1#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#5 cl1#Y cl1#a_2_6# GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX1
* pattern code: [INVX1,AND2X1]
* 345 occurrences in design 
* each contains 2 cells
* Example occurence:
*   .subckt INVX1 A=w1_28802 Y=asqrt[51]
*   .subckt AND2X1 A=w1_11969 B=w1_06346 Y=w1_28802
