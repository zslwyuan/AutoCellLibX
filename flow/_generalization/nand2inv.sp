.subckt nand2inv VCC a b yn y GND
Mg0_M0 g0#a_2_6# b VCC VCC PMOS W=0.5u L=0.05u
Mg0_M1 VCC a g0#a_2_6# VCC PMOS W=0.5u L=0.05u
Mg0_M2 y g0#a_2_6# VCC VCC PMOS W=0.5u L=0.05u
Mg0_M3 g0#a_9_6# b g0#a_2_6# GND NMOS W=0.5u L=0.05u
Mg0_M4 GND a g0#a_9_6# GND NMOS W=0.5u L=0.05u
Mg0_M5 y g0#a_2_6# GND GND NMOS W=0.25u L=0.05u
Mg1_M0 yn b VCC VCC PMOS W=0.5u L=0.05u
Mg1_M1 VCC a yn VCC PMOS W=0.5u L=0.05u
Mg1_M2 g1#a_9_6# b GND GND NMOS W=0.5u L=0.05u
Mg1_M3 yn a g1#a_9_6# GND NMOS W=0.5u L=0.05u
.ends nand2inv
