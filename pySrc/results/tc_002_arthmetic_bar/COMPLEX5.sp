.subckt COMPLEX5 VCC cl1#Y cl2#A cl0#S GND cl2#Y cl1#A cl0#Y
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
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl1#1 cl1#Y cl1#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#0 cl2#Y cl2#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
Mcl2#1 cl2#Y cl2#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u 
.ends COMPLEX5
* pattern code: [MUX2X1,INVX1,INVX1]
* 59 occurrences in design 
* each contains 3 cells
* Example occurence:
*   .subckt MUX2X1 A=w1_1239 B=w1_1161 S=shift[0] Y=w1_0533
*   .subckt INVX1 A=a[36] Y=w1_1239
*   .subckt INVX1 A=a[37] Y=w1_1161
