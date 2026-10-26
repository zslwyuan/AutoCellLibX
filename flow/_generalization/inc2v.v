/* Hold-out module 19: 2-bit incrementer with carry out (an adder
 * slice against the constant 1 -- not in the dev set).  Scalar ports,
 * see add2sum. */
module inc2v(output q0, output q1, output q2, input a0, input a1);
  wire [2:0] inc = {1'b0, a1, a0} + 2'd1;
  assign q0 = inc[0];
  assign q1 = inc[1];
  assign q2 = inc[2];
endmodule
