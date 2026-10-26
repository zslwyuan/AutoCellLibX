/* Hold-out module 05: plain AND (NAND + inverter inside the library). */
module and2v(output y, input a, b);
  assign y = a & b;
endmodule
