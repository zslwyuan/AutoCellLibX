.subckt xor2v VCC a b y GND
Mg0_M0 VCC b g0#a_2_6# VCC PMOS W=1u L=0.05u
Mg0_M1 g0#a_18_54# g0#a_13_43# VCC VCC PMOS W=1u L=0.05u
Mg0_M2 y b g0#a_18_54# VCC PMOS W=1u L=0.05u
Mg0_M3 g0#a_35_54# g0#a_2_6# y VCC PMOS W=1u L=0.05u
Mg0_M4 VCC a g0#a_35_54# VCC PMOS W=1u L=0.05u
Mg0_M5 g0#a_13_43# a VCC VCC PMOS W=1u L=0.05u
Mg0_M6 GND b g0#a_2_6# GND NMOS W=0.5u L=0.05u
Mg0_M7 g0#a_18_6# g0#a_13_43# GND GND NMOS W=0.5u L=0.05u
Mg0_M8 y g0#a_2_6# g0#a_18_6# GND NMOS W=0.5u L=0.05u
Mg0_M9 g0#a_35_6# b y GND NMOS W=0.5u L=0.05u
Mg0_M10 GND a g0#a_35_6# GND NMOS W=0.5u L=0.05u
Mg0_M11 g0#a_13_43# a GND GND NMOS W=0.5u L=0.05u
.ends xor2v
