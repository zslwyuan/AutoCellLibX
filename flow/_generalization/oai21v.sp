.subckt oai21v VCC a b c y GND
Mg0_M0 g0#a_9_54# b VCC VCC PMOS W=1u L=0.05u
Mg0_M1 y a g0#a_9_54# VCC PMOS W=1u L=0.05u
Mg0_M2 VCC c y VCC PMOS W=0.5u L=0.05u
Mg0_M3 GND b g0#a_2_6# GND NMOS W=0.5u L=0.05u
Mg0_M4 g0#a_2_6# a GND GND NMOS W=0.5u L=0.05u
Mg0_M5 y c g0#a_2_6# GND NMOS W=0.5u L=0.05u
.ends oai21v
