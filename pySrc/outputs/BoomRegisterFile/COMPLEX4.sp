.subckt COMPLEX4 cl1#B cl1#A cl1#C cl0#Y cl0#B cl0#A GND VCC
Mcl0#0 cl0#a_9_54# cl0#A VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#Y cl0#B cl0#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 VCC cl1#Y cl0#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 GND cl0#A cl0#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#4 cl0#a_2_6# cl0#B GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#5 cl0#Y cl1#Y cl0#a_2_6# GND NMOS W=0.5u L=0.05u
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
.ends COMPLEX4
* pattern code: [OAI21X1,AOI21X1]
* 1035 occurrences in design 
* each contains 2 cells
* Example occurence:
*   .subckt OAI21X1 A=$\regfile$rdreg[2]$q[2] B=regfile[49][1] C=$abc$48160$new_n12499_ Y=$abc$48160$new_n12500_
*   .subckt AOI21X1 A=$\regfile$rdreg[2]$q[2] B=$abc$48160$new_n8795_ C=$abc$48160$new_n8689_ Y=$abc$48160$new_n12499_
