.subckt COMPLEX7 GND cl1#A cl0#Y VCC cl0#A cl1#Y
Mcl0#0 cl0#Y cl0#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 VCC cl1#Y cl0#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#a_9_6# cl0#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#Y cl1#Y cl0#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#Y cl1#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX7
* pattern code: [NAND2X1,INVX1]
* 39 occurrences in design 
* each contains 2 cells
* Example occurence:
*   .subckt NAND2X1 A=in3[98] B=$abc$13693$new_n673_ Y=$abc$13693$new_n1017_
*   .subckt INVX1 A=in2[98] Y=$abc$13693$new_n673_
