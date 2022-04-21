.subckt COMPLEX5 VCC cl1#Y cl0#Y GND cl1#A cl1#B
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
.ends COMPLEX5
* pattern code: [INVX1,AND2X1]
* 1857 occurrences in design 
* each contains 2 cells
* Example occurence:
*   .subckt INVX1 A=w1_000958 Y=hypotenuse[122]
*   .subckt AND2X1 A=w1_041501 B=w1_160702 Y=w1_000958
