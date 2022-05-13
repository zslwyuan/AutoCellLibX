.subckt COMPLEX1 cl3#A cl4#B cl2#A cl1#B cl1#A cl1#Y cl3#Y cl2#B cl4#Y cl2#C GND VCC cl0#Y cl3#B
Mcl0#0 VCC cl1#Y cl0#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#a_2_54# cl2#Y VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#Y cl3#Y cl0#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#a_12_6# cl1#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#4 cl0#Y cl2#Y cl0#a_12_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#5 GND cl3#Y cl0#Y GND NMOS W=0.25u L=0.05u
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
Mcl2#0 cl2#a_9_54# cl2#A VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 cl2#Y cl2#B cl2#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 VCC cl2#C cl2#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 GND cl2#A cl2#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#4 cl2#a_2_6# cl2#B GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#5 cl2#Y cl2#C cl2#a_2_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#0 cl3#Y cl3#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#1 VCC cl3#B cl3#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#2 cl3#a_9_6# cl3#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#3 cl3#Y cl3#B cl3#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#0 VCC cl1#Y cl4#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#1 cl4#a_2_54# cl4#B VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#2 cl4#Y cl3#Y cl4#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#3 cl4#a_12_6# cl1#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#4 cl4#Y cl4#B cl4#a_12_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#5 GND cl3#Y cl4#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX1
* pattern code: [AOI21X1,AND2X1,OAI21X1,NAND2X1]+AOI21X1_c1o0c3o0
* 57 occurrences in design 
* each contains 5 cells
* Example occurence:
*   .subckt AOI21X1 A=$abc$59024$new_n742_ B=$abc$59024$new_n881_ C=$abc$59024$new_n886_ Y=$abc$59024$new_n887_
*   .subckt AND2X1 A=$abc$59024$new_n739_ B=$abc$59024$new_n740_ Y=$abc$59024$new_n742_
*   .subckt OAI21X1 A=$abc$59024$new_n748_ B=$abc$59024$new_n875_ C=$abc$59024$new_n879_ Y=$abc$59024$new_n881_
*   .subckt NAND2X1 A=$abc$59024$new_n459_ B=$abc$59024$new_n883_ Y=$abc$59024$new_n886_
*   .subckt AOI21X1 A=$abc$59024$new_n742_ B=$abc$59024$new_n2672_ C=$abc$59024$new_n886_ Y=$abc$59024$new_n2673_
