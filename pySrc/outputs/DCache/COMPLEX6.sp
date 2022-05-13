.subckt COMPLEX6 cl2#A cl0#Y cl1#B VCC cl1#S cl2#S cl1#Y cl2#B GND cl0#S cl1#A
Mcl0#0 VCC cl0#S cl0#a_2_10# VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#a_17_50# cl2#Y VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#2 cl0#Y cl0#S cl0#a_17_50# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#3 cl0#a_30_54# cl0#a_2_10# cl0#Y VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#4 VCC cl1#Y cl0#a_30_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#5 GND cl0#S cl0#a_2_10# GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#6 cl0#a_17_10# cl2#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#7 cl0#Y cl0#a_2_10# cl0#a_17_10# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#8 cl0#a_30_10# cl0#S cl0#Y GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#9 GND cl1#Y cl0#a_30_10# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#0 VCC cl1#S cl1#a_2_10# VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#a_17_50# cl1#B VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#2 cl1#Y cl1#S cl1#a_17_50# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#3 cl1#a_30_54# cl1#a_2_10# cl1#Y VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#4 VCC cl1#A cl1#a_30_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#5 GND cl1#S cl1#a_2_10# GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#6 cl1#a_17_10# cl1#B GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#7 cl1#Y cl1#a_2_10# cl1#a_17_10# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#8 cl1#a_30_10# cl1#S cl1#Y GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#9 GND cl1#A cl1#a_30_10# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#0 VCC cl2#S cl2#a_2_10# VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 cl2#a_17_50# cl2#B VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 cl2#Y cl2#S cl2#a_17_50# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 cl2#a_30_54# cl2#a_2_10# cl2#Y VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#4 VCC cl2#A cl2#a_30_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#5 GND cl2#S cl2#a_2_10# GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#6 cl2#a_17_10# cl2#B GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#7 cl2#Y cl2#a_2_10# cl2#a_17_10# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#8 cl2#a_30_10# cl2#S cl2#Y GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#9 GND cl2#A cl2#a_30_10# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX6
* pattern code: [MUX2X1,MUX2X1,MUX2X1]
* 6579 occurrences in design 
* each contains 3 cells
* Example occurence:
*   .subckt MUX2X1 A=$abc$1066023$new_n284041_ B=$abc$1066023$new_n286077_ S=get_a_mask_bit_3 Y=$abc$1066023$new_n286078_
*   .subckt MUX2X1 A=io_cpu_resp_bits_data_word_bypass[8] B=io_cpu_resp_bits_data_word_bypass[24] S=$abc$1066023$new_n280675_ Y=$abc$1066023$new_n284041_
*   .subckt MUX2X1 A=io_cpu_resp_bits_data_word_bypass[0] B=io_cpu_resp_bits_data_word_bypass[16] S=$abc$1066023$new_n280675_ Y=$abc$1066023$new_n286077_
