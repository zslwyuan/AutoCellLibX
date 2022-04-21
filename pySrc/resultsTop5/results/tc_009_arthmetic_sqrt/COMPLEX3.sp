.subckt COMPLEX3 VCC cl1#Y cl0#Y GND cl1#A cl1#B
Mcl0#0 cl0#Y cl1#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#Y cl1#Y GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#a_9_54# cl1#A VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#Y cl1#B cl1#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#2 cl1#Y cl1#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#3 GND cl1#B cl1#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX3
* pattern code: [INVX1,NOR2X1]
* 272 occurrences in design 
* each contains 2 cells
* Example occurence:
*   .subckt INVX1 A=w1_23796 Y=asqrt[59]
*   .subckt NOR2X1 A=w1_13034 B=w1_08267 Y=w1_23796
