/* Hold-out module 17: 4:1 multiplexer (a three-MUX tree).  Scalar
 * select ports, see add2sum. */
module mux4v(output y, input a, input b, input c, input d,
             input s0, input s1);
  assign y = s1 ? (s0 ? d : c) : (s0 ? b : a);
endmodule
