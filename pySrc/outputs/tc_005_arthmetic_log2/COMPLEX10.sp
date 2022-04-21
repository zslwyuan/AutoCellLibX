.subckt COMPLEX10 VCC GND cl1#A cl1#B cl1#C
Mcl0#0 cl0#Y cl1#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#Y cl1#Y GND GND NMOS W=0.25u L=0.05u
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
.ends COMPLEX10
* pattern code: [INVX1,OAI21X1]
* 188 occurrences in design 
* each contains 2 cells
* Example occurence:
*   .subckt INVX1 A=w1_00268 Y=result[11]
*   .subckt OAI21X1 A=w1_19396 B=w1_07965 C=w1_22745 Y=w1_00268
