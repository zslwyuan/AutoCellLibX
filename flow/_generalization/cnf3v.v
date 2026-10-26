/* Hold-out module 10: majority of 3 in CNF form -- same function as
 * maj3v, a different factoring for the technology mapper. */
module cnf3v(output y, input a, b, c);
  assign y = (a | b) & (b | c) & (a | c);
endmodule
