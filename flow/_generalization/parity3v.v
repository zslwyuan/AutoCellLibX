/* Hold-out module 16: parity of 3 (two chained XORs -- a wider
 * crossover tree than any closing dev cell). */
module parity3v(output y, input a, b, c);
  assign y = a ^ b ^ c;
endmodule
