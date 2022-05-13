.subckt COMPLEX12 VCC cl2#B cl0#Y cl2#C cl1#A cl2#A cl1#B cl2#D GND
Mcl0#0 cl0#Y cl1#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 VCC cl2#Y cl0#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#a_9_6# cl1#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#Y cl2#Y cl0#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 VCC cl1#B cl1#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#2 cl1#a_9_6# cl1#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#3 cl1#Y cl1#B cl1#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#0 VCC cl2#A cl2#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 cl2#a_2_54# cl2#B VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 cl2#Y cl2#D cl2#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 cl2#a_2_54# cl2#C cl2#Y VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#4 cl2#a_11_6# cl2#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#5 cl2#Y cl2#B cl2#a_11_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#6 cl2#a_28_6# cl2#D cl2#Y GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#7 GND cl2#C cl2#a_28_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX12
* pattern code: [NAND2X1,NAND2X1,AOI22X1]
* 128 occurrences in design 
* each contains 3 cells
* Example occurence:
*   .subckt NAND2X1 A=$abc$84033$new_n30772_ B=$abc$84033$new_n30773_ Y=$abc$84033$auto$rtlil.cc:2551:MuxGate$84028
*   .subckt NAND2X1 A=io_fflags_1_bits_flags[2] B=$abc$84033$new_n30761_ Y=$abc$84033$new_n30772_
*   .subckt AOI22X1 A=rob_fflags[7][2] B=$abc$84033$new_n30764_ C=$abc$84033$new_n30765_ D=io_fflags_0_bits_flags[2] Y=$abc$84033$new_n30773_
