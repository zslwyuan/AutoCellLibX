/* Hold-out module 04: OR-AND-INVERT 2-1 (the dual AOI form). */
module oai21v(output y, input a, b, c);
  assign y = ~((a | b) & c);
endmodule
