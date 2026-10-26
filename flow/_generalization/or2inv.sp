.subckt or2inv VCC a b y yn GND
Mg0_M0 g0#a_9_54# b VCC VCC PMOS W=1u L=0.05u
Mg0_M1 yn a g0#a_9_54# VCC PMOS W=1u L=0.05u
Mg0_M2 yn b GND GND NMOS W=0.25u L=0.05u
Mg0_M3 GND a yn GND NMOS W=0.25u L=0.05u
Mg1_M0 g1#a_9_54# b g1#a_2_54# VCC PMOS W=1u L=0.05u
Mg1_M1 VCC a g1#a_9_54# VCC PMOS W=1u L=0.05u
Mg1_M2 y g1#a_2_54# VCC VCC PMOS W=0.5u L=0.05u
Mg1_M3 g1#a_2_54# b GND GND NMOS W=0.25u L=0.05u
Mg1_M4 GND a g1#a_2_54# GND NMOS W=0.25u L=0.05u
Mg1_M5 y g1#a_2_54# GND GND NMOS W=0.25u L=0.05u
.ends or2inv
