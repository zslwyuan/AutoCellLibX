/* Hold-out module 07: two-output OR/NOR pair. */
module or2inv(output y, output yn, input a, b);
  assign y  = a | b;
  assign yn = ~y;
endmodule
