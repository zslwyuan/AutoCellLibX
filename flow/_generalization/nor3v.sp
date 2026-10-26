.subckt nor3v VCC a b c y GND
Mg0_M0 VCC b g0#a_2_64# VCC PMOS W=0.75u L=0.05u
Mg0_M1 g0#a_2_64# b VCC VCC PMOS W=0.75u L=0.05u
Mg0_M2 g0#a_25_64# a g0#a_2_64# VCC PMOS W=0.75u L=0.05u
Mg0_M3 g0#a_2_64# a g0#a_25_64# VCC PMOS W=0.75u L=0.05u
Mg0_M4 y c g0#a_25_64# VCC PMOS W=0.75u L=0.05u
Mg0_M5 g0#a_25_64# c y VCC PMOS W=0.75u L=0.05u
Mg0_M6 y b GND GND NMOS W=0.25u L=0.05u
Mg0_M7 GND a y GND NMOS W=0.25u L=0.05u
Mg0_M8 y c GND GND NMOS W=0.25u L=0.05u
.ends nor3v
