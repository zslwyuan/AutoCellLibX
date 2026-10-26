/* Hold-out module 13: 2:1 multiplexer.
 * Dev-set context: MUX2X1 (10T) is an unsupported wall on the dev
 * set (its production closure is one selection-policy step away,
 * AUDIT 5.59) -- the hold-out spelling runs today's ladder. */
module mux2v(output y, input a, b, s);
  assign y = s ? b : a;
endmodule
