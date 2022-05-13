.subckt COMPLEX29 cl2#A cl1#B cl1#A cl1#Y cl3#Y cl2#B cl4#C cl5#C cl4#Y cl5#Y GND VCC cl4#A cl3#C cl0#Y cl5#B cl3#B cl2#Y
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
Mcl2#0 cl2#Y cl2#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 VCC cl2#B cl2#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 cl2#a_9_6# cl2#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 cl2#Y cl2#B cl2#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#0 cl3#Y cl2#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#1 VCC cl3#B cl3#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#2 cl3#Y cl3#C VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#3 cl3#a_9_6# cl2#Y GND GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#4 cl3#a_14_6# cl3#B cl3#a_9_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl3#5 cl3#Y cl3#C cl3#a_14_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#0 cl4#Y cl4#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#1 VCC cl1#Y cl4#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#2 cl4#Y cl4#C VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#3 cl4#a_9_6# cl4#A GND GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#4 cl4#a_14_6# cl1#Y cl4#a_9_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl4#5 cl4#Y cl4#C cl4#a_14_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl5#0 cl5#Y cl2#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl5#1 VCC cl5#B cl5#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl5#2 cl5#Y cl5#C VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl5#3 cl5#a_9_6# cl2#Y GND GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl5#4 cl5#a_14_6# cl5#B cl5#a_9_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl5#5 cl5#Y cl5#C cl5#a_14_6# GND NMOS W=0.75u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX29
* pattern code: [NAND2X1,NAND2X1,NAND2X1]+NAND3X1_c2o0+NAND3X1_c1o0+NAND3X1_c2o0
* 29 occurrences in design 
* each contains 6 cells
* Example occurence:
*   .subckt NAND2X1 A=$abc$24906$new_n198_ B=$abc$24906$new_n199_ Y=$abc$24906$new_n200_
*   .subckt NAND2X1 A=$abc$24906$new_n70_ B=$abc$24906$new_n196_ Y=$abc$24906$new_n198_
*   .subckt NAND2X1 A=$abc$24906$new_n101_ B=$abc$24906$new_n127_ Y=$abc$24906$new_n199_
*   .subckt NAND3X1 A=$abc$24906$new_n199_ B=$abc$24906$new_n240_ C=$abc$24906$new_n641_ Y=$abc$24906$new_n642_
*   .subckt NAND3X1 A=$abc$24906$new_n134_ B=$abc$24906$new_n198_ C=$abc$24906$new_n328_ Y=$abc$24906$new_n639_
*   .subckt NAND3X1 A=$abc$24906$new_n199_ B=$abc$24906$new_n355_ C=$abc$24906$new_n1176_ Y=$abc$24906$new_n1178_
