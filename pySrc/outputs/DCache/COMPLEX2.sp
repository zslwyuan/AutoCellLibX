.subckt COMPLEX2 cl0#A cl2#A cl1#B cl4#B VCC cl3#Y cl2#B GND cl1#A cl3#A cl4#A
Mcl0#0 cl0#Y cl0#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 VCC cl1#Y cl0#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#Y cl2#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#a_9_6# cl0#A GND GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#4 cl0#a_14_6# cl1#Y cl0#a_9_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#5 cl0#Y cl2#Y cl0#a_14_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 VCC cl1#B cl1#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#2 cl1#a_9_6# cl1#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#3 cl1#Y cl1#B cl1#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#0 cl2#Y cl2#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 VCC cl2#B cl2#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 cl2#a_9_6# cl2#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 cl2#Y cl2#B cl2#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#0 cl3#Y cl3#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#1 VCC cl0#Y cl3#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#2 cl3#Y cl4#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#3 cl3#a_9_6# cl3#A GND GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#4 cl3#a_14_6# cl0#Y cl3#a_9_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#5 cl3#Y cl4#Y cl3#a_14_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#0 cl4#Y cl4#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#1 VCC cl4#B cl4#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#2 cl4#a_9_6# cl4#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#3 cl4#Y cl4#B cl4#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX2
* pattern code: [NAND3X1,NAND2X1,NAND2X1]+NAND3X1_c0o0+NAND2X1_c3i0
* 8903 occurrences in design 
* each contains 5 cells
* Example occurence:
*   .subckt NAND3X1 A=$\tag_array.tag_array_ext.mem_0_0.ram$rdreg[0]$q[3] B=$abc$1066023$new_n294835_ C=$abc$1066023$new_n294837_ Y=$abc$1066023$new_n294838_
*   .subckt NAND2X1 A=$abc$1066023$new_n279781_ B=$abc$1066023$new_n294834_ Y=$abc$1066023$new_n294835_
*   .subckt NAND2X1 A=$\tag_array.tag_array_ext.mem_0_0.ram$rdreg[0]$q[0] B=$abc$1066023$new_n294836_ Y=$abc$1066023$new_n294837_
*   .subckt NAND3X1 A=$\tag_array.tag_array_ext.mem_0_0.ram$rdreg[0]$q[1] B=$abc$1066023$new_n294838_ C=$abc$1066023$new_n294842_ Y=$abc$1066023$new_n294843_
*   .subckt NAND2X1 A=$abc$1066023$new_n279786_ B=$abc$1066023$new_n294841_ Y=$abc$1066023$new_n294842_
