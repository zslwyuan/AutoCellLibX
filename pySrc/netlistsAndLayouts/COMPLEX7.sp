.subckt COMPLEX7 cl1#Y GND cl0#B cl1#A VCC cl0#Y cl0#C
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
.ends COMPLEX7
* pattern code: [AOI21X1,INVX1]
* 454 occurrences in design 
* each contains 2 cells
* Example occurence:
*   .subckt AOI21X1 A=$abc$1084410$new_n266344_ B=banked_predictors_0.components_1.tables_1.io_f3_resp_3_valid_REG C=banked_predictors_0.components_1.tables_3.io_f3_resp_3_valid_REG Y=$abc$1084410$new_n293066_
*   .subckt INVX1 A=banked_predictors_0.components_1.tables_2.io_f3_resp_3_valid_REG Y=$abc$1084410$new_n266344_
