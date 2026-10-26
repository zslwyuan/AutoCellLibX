/* Hold-out module 08: OR-AND-INVERT 2-2 (the dual of aoi22v --
 * two sum terms into one inverting gate). */
module oai22v(output y, input a, b, c, d);
  assign y = ~((a | b) & (c | d));
endmodule
