.subckt COMPLEX1 GND cl1#A cl0#Y cl1#C VCC cl0#A cl1#B
Mcl0#0 VCC cl0#A cl0#a_2_6# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#a_18_54# cl0#a_12_41# VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#Y cl0#a_2_6# cl0#a_18_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#a_35_54# cl0#A cl0#Y VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#4 VCC cl1#Y cl0#a_35_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#5 cl0#a_12_41# cl1#Y VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#6 GND cl0#A cl0#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#7 cl0#a_18_6# cl0#a_12_41# GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#8 cl0#Y cl0#A cl0#a_18_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#9 cl0#a_35_6# cl0#a_2_6# cl0#Y GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#10 GND cl1#Y cl0#a_35_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#11 cl0#a_12_41# cl1#Y GND GND NMOS W=0.5u L=0.05u
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
.ends COMPLEX1
* pattern code: [XNOR2X1,AOI21X1]
* 466 occurrences in design 
* each contains 2 cells
* Example occurence:
*   .subckt XNOR2X1 A=a[23] B=$abc$148607$new_n2630_ Y=$abc$148607$new_n2631_
*   .subckt AOI21X1 A=$abc$148607$new_n96_ B=$abc$148607$new_n2617_ C=$abc$148607$new_n2629_ Y=$abc$148607$new_n2630_
