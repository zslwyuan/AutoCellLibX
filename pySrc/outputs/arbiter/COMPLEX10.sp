.subckt COMPLEX10 VCC cl0#Y cl1#A cl1#Y cl0#B GND
Mcl0#0 cl0#Y cl1#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 VCC cl0#B cl0#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#a_9_6# cl1#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#Y cl0#B cl0#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#Y cl1#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX10
* pattern code: [NAND2X1,INVX1]
* 116 occurrences in design 
* each contains 2 cells
* Example occurence:
*   .subckt NAND2X1 A=$abc$59024$new_n597_ B=req[124] Y=$abc$59024$new_n605_
*   .subckt INVX1 A=priority[125] Y=$abc$59024$new_n597_
