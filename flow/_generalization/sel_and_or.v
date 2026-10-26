/* Hold-out module 15: select between an AND term and an OR term --
 * a mux feeding data that still needs gating (two-level composition). */
module sel_and_or(output y, input a, b, c, d, en);
  assign y = en ? (a & b) : (c | d);
endmodule
