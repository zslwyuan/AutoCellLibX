/* Hold-out module 02: AND-OR-INVERT 2-1 (single complex gate). */
module aoi21v(output y, input a, b, c);
  assign y = ~((a & b) | c);
endmodule
