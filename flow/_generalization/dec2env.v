/* Hold-out module 21: 2-to-4 decoder with enable (four-bit one-hot
 * output -- a multi-output hold-out cell).  Scalar ports, see
 * add2sum. */
module dec2env(output y0, output y1, output y2, output y3,
               input en, input s0, input s1);
  assign y0 = en & ~s1 & ~s0;
  assign y1 = en & ~s1 & s0;
  assign y2 = en & s1 & ~s0;
  assign y3 = en & s1 & s0;
endmodule
