.subckt COMPLEX28 VCC cl1#Y cl2#A GND cl1#S cl2#Y cl1#A cl1#B cl0#Y cl2#S
Mcl0#0 cl0#Y cl1#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl0#1 cl0#Y cl1#Y GND GND NMOS W=0.25u L=0.05u
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
Mcl2#1 cl2#a_17_50# cl0#Y VCC VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#2 cl2#Y cl2#S cl2#a_17_50# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#3 cl2#a_30_54# cl2#a_2_10# cl2#Y VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#4 VCC cl2#A cl2#a_30_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#5 GND cl2#S cl2#a_2_10# GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#6 cl2#a_17_10# cl0#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#7 cl2#Y cl2#a_2_10# cl2#a_17_10# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#8 cl2#a_30_10# cl2#S cl2#Y GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#9 GND cl2#A cl2#a_30_10# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX28
* pattern code: [INVX1,MUX2X1]+c0o0_MUX2X1
* 231 occurrences in design 
* each contains 3 cells
* Example occurence:
*   .subckt INVX1 A=w1_22220 Y=w1_35371
*   .subckt MUX2X1 A=w1_22207 B=w1_22732 S=quotient[38] Y=w1_22220
*   .subckt MUX2X1 A=w1_22703 B=w1_35371 S=w1_09787 Y=w1_06534
