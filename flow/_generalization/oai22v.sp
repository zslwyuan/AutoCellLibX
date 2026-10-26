.subckt oai22v VCC a b c d y GND
Mg0_M0 g0#a_9_54# d g0#a_2_54# VCC PMOS W=1u L=0.05u
Mg0_M1 VCC c g0#a_9_54# VCC PMOS W=1u L=0.05u
Mg0_M2 _0_ g0#a_2_54# VCC VCC PMOS W=0.5u L=0.05u
Mg0_M3 g0#a_2_54# d GND GND NMOS W=0.25u L=0.05u
Mg0_M4 GND c g0#a_2_54# GND NMOS W=0.25u L=0.05u
Mg0_M5 _0_ g0#a_2_54# GND GND NMOS W=0.25u L=0.05u
Mg1_M0 g1#a_9_54# b VCC VCC PMOS W=1u L=0.05u
Mg1_M1 y a g1#a_9_54# VCC PMOS W=1u L=0.05u
Mg1_M2 VCC _0_ y VCC PMOS W=0.5u L=0.05u
Mg1_M3 GND b g1#a_2_6# GND NMOS W=0.5u L=0.05u
Mg1_M4 g1#a_2_6# a GND GND NMOS W=0.5u L=0.05u
Mg1_M5 y _0_ g1#a_2_6# GND NMOS W=0.5u L=0.05u
.ends oai22v
