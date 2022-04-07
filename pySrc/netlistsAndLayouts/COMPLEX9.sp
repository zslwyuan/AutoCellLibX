.subckt COMPLEX9 cl2#A cl1#Y GND cl0#A cl1#A VCC cl0#Y cl2#Y
Mcl0#0 VCC cl0#A cl0#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#a_2_54# cl1#Y VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#Y cl2#Y cl0#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#a_12_6# cl0#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#4 cl0#Y cl1#Y cl0#a_12_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#5 GND cl2#Y cl0#Y GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#Y cl1#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#0 cl2#Y cl2#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 cl2#Y cl2#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX9
* pattern code: [AOI21X1,INVX1,INVX1]
* 3 occurrences in design 
* each contains 3 cells
* Example occurence:
*   .subckt AOI21X1 A=banked_predictors_0.components_1.tables_3.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[2] B=$abc$1084410$new_n266666_ C=$abc$1084410$new_n266615_ Y=$abc$1084410$new_n295345_
*   .subckt INVX1 A=banked_predictors_0.components_1.tables_3.hi_us.hi_us_0_ext.mem_0_0.ram[255] Y=$abc$1084410$new_n266666_
*   .subckt INVX1 A=banked_predictors_0.components_1.tables_3.table_.table_0_ext.mem_0_3.ram_R_0_addr_pipe_0[0] Y=$abc$1084410$new_n266615_
