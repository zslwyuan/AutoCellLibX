.subckt aoi21v VCC a b c y GND
Mg0_M0 VCC b g0#a_2_54# VCC PMOS W=1u L=0.05u
Mg0_M1 g0#a_2_54# a VCC VCC PMOS W=1u L=0.05u
Mg0_M2 y c g0#a_2_54# VCC PMOS W=1u L=0.05u
Mg0_M3 g0#a_12_6# b GND GND NMOS W=0.5u L=0.05u
Mg0_M4 y a g0#a_12_6# GND NMOS W=0.5u L=0.05u
Mg0_M5 GND c y GND NMOS W=0.25u L=0.05u
.ends aoi21v
