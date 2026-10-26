/* Hold-out module 11: XOR of 2.
 * Dev-set context: XOR2X1 (12T) is an unsupported wall on the dev
 * set -- a fresh spelling re-probes the crossover class. */
module xor2v(output y, input a, b);
  assign y = a ^ b;
endmodule
