/* Hold-out module 18: 2-bit adder slice, sum bits only (the carry
 * out is dropped -- a smaller adder slice than the dev set's HAX1/
 * FAX1, and a different function).  Ports are scalar: the flatten
 * step's bus handling predates this set, and a fresh module must not
 * lean on it. */
module add2sum(output s0, output s1,
               input a0, input a1, input b0, input b1);
  wire [2:0] sum = {1'b0, a1, a0} + {1'b0, b1, b0};
  assign s0 = sum[0];
  assign s1 = sum[1];
endmodule
