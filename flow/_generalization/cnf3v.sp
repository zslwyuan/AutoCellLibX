.subckt cnf3v VCC a b c y GND
Mg0_M0 _0_ b VCC VCC PMOS W=0.5u L=0.05u
Mg0_M1 VCC c _0_ VCC PMOS W=0.5u L=0.05u
Mg0_M2 g0#a_9_6# b GND GND NMOS W=0.5u L=0.05u
Mg0_M3 _0_ c g0#a_9_6# GND NMOS W=0.5u L=0.05u
Mg1_M0 g1#a_9_54# b VCC VCC PMOS W=1u L=0.05u
Mg1_M1 _1_ c g1#a_9_54# VCC PMOS W=1u L=0.05u
Mg1_M2 VCC a _1_ VCC PMOS W=0.5u L=0.05u
Mg1_M3 GND b g1#a_2_6# GND NMOS W=0.5u L=0.05u
Mg1_M4 g1#a_2_6# c GND GND NMOS W=0.5u L=0.05u
Mg1_M5 _1_ a g1#a_2_6# GND NMOS W=0.5u L=0.05u
Mg2_M0 y _0_ VCC VCC PMOS W=0.5u L=0.05u
Mg2_M1 VCC _1_ y VCC PMOS W=0.5u L=0.05u
Mg2_M2 g2#a_9_6# _0_ GND GND NMOS W=0.5u L=0.05u
Mg2_M3 y _1_ g2#a_9_6# GND NMOS W=0.5u L=0.05u
.ends cnf3v
