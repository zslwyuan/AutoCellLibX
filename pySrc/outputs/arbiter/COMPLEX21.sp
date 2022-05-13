.subckt COMPLEX21 VCC cl0#Y cl1#A cl1#Y cl0#C cl0#B GND
Mcl0#0 VCC cl1#Y cl0#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#a_2_54# cl0#B VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#Y cl0#C cl0#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#a_12_6# cl1#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#4 cl0#Y cl0#B cl0#a_12_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#5 GND cl0#C cl0#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#Y cl1#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX21
* pattern code: [AOI21X1,INVX1]
* 52 occurrences in design 
* each contains 2 cells
* Example occurence:
*   .subckt AOI21X1 A=$abc$59024$new_n395_ B=priority[6] C=priority[7] Y=$abc$59024$new_n811_
*   .subckt INVX1 A=req[6] Y=$abc$59024$new_n395_
