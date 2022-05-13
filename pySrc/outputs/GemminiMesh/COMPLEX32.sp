.subckt COMPLEX32 cl0#Y cl4#B cl2#Y GND cl3#B cl1#B cl4#A cl2#B cl4#Y cl3#C VCC
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
Mcl3#0 cl3#a_9_54# cl4#Y VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#1 cl3#Y cl3#B cl3#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#2 VCC cl3#C cl3#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#3 GND cl4#Y cl3#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#4 cl3#a_2_6# cl3#B GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#5 cl3#Y cl3#C cl3#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#0 cl4#Y cl4#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#1 VCC cl4#B cl4#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#2 cl4#a_9_6# cl4#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#3 cl4#Y cl4#B cl4#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX32
* pattern code: [NAND2X1,OR2X1,NAND2X1]+OAI21X1_c1i0c2i0+NAND2X1_c3i0
* 259 occurrences in design 
* each contains 5 cells
* Example occurence:
*   .subckt NAND2X1 A=$abc$171717$new_n6102_ B=$abc$171717$new_n6103_ Y=$abc$171717$new_n6104_
*   .subckt OR2X1 A=$abc$171717$new_n6094_ B=$abc$171717$new_n6101_ Y=$abc$171717$new_n6102_
*   .subckt NAND2X1 A=$abc$171717$new_n6094_ B=$abc$171717$new_n6101_ Y=$abc$171717$new_n6103_
*   .subckt OAI21X1 A=$abc$171717$new_n6072_ B=$abc$171717$new_n6075_ C=$abc$171717$new_n6074_ Y=$abc$171717$new_n6094_
*   .subckt NAND2X1 A=mesh_3_0.tile_0_0.c2[1] B=r_12_0[0] Y=$abc$171717$new_n6072_
