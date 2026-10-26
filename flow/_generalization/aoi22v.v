/* Hold-out module 03: AND-OR-INVERT 2-2 (single complex gate,
 * two product terms -- a wider AOI than any single-gate dev cell). */
module aoi22v(output y, input a, b, c, d);
  assign y = ~((a & b) | (c & d));
endmodule
