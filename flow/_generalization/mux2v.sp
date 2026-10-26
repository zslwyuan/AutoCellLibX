.subckt mux2v VCC a b s y GND
Mg0_M0 VCC s g0#a_2_10# VCC PMOS W=0.5u L=0.05u
Mg0_M1 g0#a_17_50# a VCC VCC PMOS W=1u L=0.05u
Mg0_M2 _0_ s g0#a_17_50# VCC PMOS W=1u L=0.05u
Mg0_M3 g0#a_30_54# g0#a_2_10# _0_ VCC PMOS W=1u L=0.05u
Mg0_M4 VCC b g0#a_30_54# VCC PMOS W=1u L=0.05u
Mg0_M5 GND s g0#a_2_10# GND NMOS W=0.25u L=0.05u
Mg0_M6 g0#a_17_10# a GND GND NMOS W=0.5u L=0.05u
Mg0_M7 _0_ g0#a_2_10# g0#a_17_10# GND NMOS W=0.5u L=0.05u
Mg0_M8 g0#a_30_10# s _0_ GND NMOS W=0.5u L=0.05u
Mg0_M9 GND b g0#a_30_10# GND NMOS W=0.5u L=0.05u
Mg1_M0 y _0_ VCC VCC PMOS W=0.5u L=0.05u
Mg1_M1 y _0_ GND GND NMOS W=0.25u L=0.05u
.ends mux2v
