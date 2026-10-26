/* Hold-out module 06: two-output NAND/AND pair (the second output
 * keeps yosys from collapsing the pair into a single gate). */
module nand2inv(output yn, output y, input a, b);
  assign yn = ~(a & b);
  assign y  = ~yn;
endmodule
