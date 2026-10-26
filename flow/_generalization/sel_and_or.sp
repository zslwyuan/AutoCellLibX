.subckt sel_and_or VCC a b c d en y GND
Mg0_M0 _0_ b VCC VCC PMOS W=0.5u L=0.05u
Mg0_M1 VCC a _0_ VCC PMOS W=0.5u L=0.05u
Mg0_M2 g0#a_9_6# b GND GND NMOS W=0.5u L=0.05u
Mg0_M3 _0_ a g0#a_9_6# GND NMOS W=0.5u L=0.05u
Mg1_M0 VCC en g1#a_2_54# VCC PMOS W=1u L=0.05u
Mg1_M1 g1#a_2_54# _0_ VCC VCC PMOS W=1u L=0.05u
Mg1_M2 y _1_ g1#a_2_54# VCC PMOS W=1u L=0.05u
Mg1_M3 g1#a_12_6# en GND GND NMOS W=0.5u L=0.05u
Mg1_M4 y _0_ g1#a_12_6# GND NMOS W=0.5u L=0.05u
Mg1_M5 GND _1_ y GND NMOS W=0.25u L=0.05u
Mg2_M0 VCC d g2#a_2_64# VCC PMOS W=0.75u L=0.05u
Mg2_M1 g2#a_2_64# d VCC VCC PMOS W=0.75u L=0.05u
Mg2_M2 g2#a_25_64# c g2#a_2_64# VCC PMOS W=0.75u L=0.05u
Mg2_M3 g2#a_2_64# c g2#a_25_64# VCC PMOS W=0.75u L=0.05u
Mg2_M4 _1_ en g2#a_25_64# VCC PMOS W=0.75u L=0.05u
Mg2_M5 g2#a_25_64# en _1_ VCC PMOS W=0.75u L=0.05u
Mg2_M6 _1_ d GND GND NMOS W=0.25u L=0.05u
Mg2_M7 GND c _1_ GND NMOS W=0.25u L=0.05u
Mg2_M8 _1_ en GND GND NMOS W=0.25u L=0.05u
.ends sel_and_or
