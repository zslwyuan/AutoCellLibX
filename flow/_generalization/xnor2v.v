/* Hold-out module 12: XNOR of 2.
 * Dev-set context: XNOR2X1 (12T) is an unsupported wall on the dev
 * set. */
module xnor2v(output y, input a, b);
  assign y = ~(a ^ b);
endmodule
