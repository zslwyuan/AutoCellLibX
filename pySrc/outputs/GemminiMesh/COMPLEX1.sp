.subckt COMPLEX1 cl0#Y GND cl3#B cl1#B cl3#A cl1#Y cl2#B cl3#C VCC cl3#Y
Mcl0#0 cl0#Y cl1#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 VCC cl2#Y cl0#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#a_9_6# cl1#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#Y cl2#Y cl0#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#a_9_54# cl3#Y cl1#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 VCC cl1#B cl1#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#2 cl1#Y cl1#a_2_54# VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#3 cl1#a_2_54# cl3#Y GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#4 GND cl1#B cl1#a_2_54# GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#5 cl1#Y cl1#a_2_54# GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#0 cl2#Y cl3#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 VCC cl2#B cl2#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 cl2#a_9_6# cl3#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 cl2#Y cl2#B cl2#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#0 cl3#a_9_54# cl3#A VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#1 cl3#Y cl3#B cl3#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#2 VCC cl3#C cl3#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#3 GND cl3#A cl3#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#4 cl3#a_2_6# cl3#B GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#5 cl3#Y cl3#C cl3#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX1
* pattern code: [NAND2X1,OR2X1,NAND2X1]+OAI21X1_c1i0c2i0
* 429 occurrences in design 
* each contains 4 cells
* Example occurence:
*   .subckt NAND2X1 A=$abc$171717$new_n5815_ B=$abc$171717$new_n5837_ Y=$abc$171717$new_n5838_
*   .subckt OR2X1 A=$abc$171717$new_n5813_ B=$abc$171717$new_n5814_ Y=$abc$171717$new_n5815_
*   .subckt NAND2X1 A=$abc$171717$new_n5813_ B=$abc$171717$new_n5814_ Y=$abc$171717$new_n5837_
*   .subckt OAI21X1 A=$abc$171717$new_n5088_ B=$abc$171717$new_n5734_ C=$abc$171717$new_n5812_ Y=$abc$171717$new_n5813_
