/* Hold-out module 20: 2-bit equality comparator (XNOR pair + AND).
 * Scalar ports, see add2sum. */
module eq2v(output eq, input a0, input a1, input b0, input b1);
  assign eq = (a0 == b0) & (a1 == b1);
endmodule
