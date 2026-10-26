/* Hold-out module 01: 3-input NOR (single inverted-OR gate).
 * Dev-set context: NOR3X1 (9T) is an unsupported wall on the 49-cell
 * benchmark -- this fresh spelling re-probes that class. */
module nor3v(output y, input a, b, c);
  assign y = ~(a | b | c);
endmodule
