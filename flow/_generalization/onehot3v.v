/* Hold-out module 14: exactly-one-hot detector over 3 inputs. */
module onehot3v(output y, input a, b, c);
  assign y = (a & ~b & ~c) | (~a & b & ~c) | (~a & ~b & c);
endmodule
