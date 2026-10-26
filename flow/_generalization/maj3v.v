/* Hold-out module 09: majority of 3 (SOP form) -- a fresh multi-gate
 * composition, not a library cell. */
module maj3v(output y, input a, b, c);
  assign y = (a & b) | (c & (a | b));
endmodule
