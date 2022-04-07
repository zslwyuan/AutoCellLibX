module cc_dir_ext(
  input  [9:0]   RW0_addr,
  input          RW0_clk,
  input  [151:0] RW0_wdata,
  output [151:0] RW0_rdata,
  input          RW0_en,
  input          RW0_wmode,
  input  [7:0]   RW0_wmask
);
  wire [9:0] mem_0_0_RW0_addr;
  wire  mem_0_0_RW0_clk;
  wire [18:0] mem_0_0_RW0_wdata;
  wire [18:0] mem_0_0_RW0_rdata;
  wire  mem_0_0_RW0_en;
  wire  mem_0_0_RW0_wmode;
  wire  mem_0_0_RW0_wmask;
  wire [9:0] mem_0_1_RW0_addr;
  wire  mem_0_1_RW0_clk;
  wire [18:0] mem_0_1_RW0_wdata;
  wire [18:0] mem_0_1_RW0_rdata;
  wire  mem_0_1_RW0_en;
  wire  mem_0_1_RW0_wmode;
  wire  mem_0_1_RW0_wmask;
  wire [9:0] mem_0_2_RW0_addr;
  wire  mem_0_2_RW0_clk;
  wire [18:0] mem_0_2_RW0_wdata;
  wire [18:0] mem_0_2_RW0_rdata;
  wire  mem_0_2_RW0_en;
  wire  mem_0_2_RW0_wmode;
  wire  mem_0_2_RW0_wmask;
  wire [9:0] mem_0_3_RW0_addr;
  wire  mem_0_3_RW0_clk;
  wire [18:0] mem_0_3_RW0_wdata;
  wire [18:0] mem_0_3_RW0_rdata;
  wire  mem_0_3_RW0_en;
  wire  mem_0_3_RW0_wmode;
  wire  mem_0_3_RW0_wmask;
  wire [9:0] mem_0_4_RW0_addr;
  wire  mem_0_4_RW0_clk;
  wire [18:0] mem_0_4_RW0_wdata;
  wire [18:0] mem_0_4_RW0_rdata;
  wire  mem_0_4_RW0_en;
  wire  mem_0_4_RW0_wmode;
  wire  mem_0_4_RW0_wmask;
  wire [9:0] mem_0_5_RW0_addr;
  wire  mem_0_5_RW0_clk;
  wire [18:0] mem_0_5_RW0_wdata;
  wire [18:0] mem_0_5_RW0_rdata;
  wire  mem_0_5_RW0_en;
  wire  mem_0_5_RW0_wmode;
  wire  mem_0_5_RW0_wmask;
  wire [9:0] mem_0_6_RW0_addr;
  wire  mem_0_6_RW0_clk;
  wire [18:0] mem_0_6_RW0_wdata;
  wire [18:0] mem_0_6_RW0_rdata;
  wire  mem_0_6_RW0_en;
  wire  mem_0_6_RW0_wmode;
  wire  mem_0_6_RW0_wmask;
  wire [9:0] mem_0_7_RW0_addr;
  wire  mem_0_7_RW0_clk;
  wire [18:0] mem_0_7_RW0_wdata;
  wire [18:0] mem_0_7_RW0_rdata;
  wire  mem_0_7_RW0_en;
  wire  mem_0_7_RW0_wmode;
  wire  mem_0_7_RW0_wmask;
  wire [18:0] RW0_rdata_0_0 = mem_0_0_RW0_rdata;
  wire [18:0] RW0_rdata_0_1 = mem_0_1_RW0_rdata;
  wire [18:0] RW0_rdata_0_2 = mem_0_2_RW0_rdata;
  wire [18:0] RW0_rdata_0_3 = mem_0_3_RW0_rdata;
  wire [18:0] RW0_rdata_0_4 = mem_0_4_RW0_rdata;
  wire [18:0] RW0_rdata_0_5 = mem_0_5_RW0_rdata;
  wire [18:0] RW0_rdata_0_6 = mem_0_6_RW0_rdata;
  wire [18:0] RW0_rdata_0_7 = mem_0_7_RW0_rdata;
  wire [37:0] _GEN_0 = {RW0_rdata_0_1,RW0_rdata_0_0};
  wire [56:0] _GEN_1 = {RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  wire [75:0] _GEN_2 = {RW0_rdata_0_3,RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  wire [94:0] _GEN_3 = {RW0_rdata_0_4,RW0_rdata_0_3,RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  wire [113:0] _GEN_4 = {RW0_rdata_0_5,RW0_rdata_0_4,RW0_rdata_0_3,RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  wire [132:0] _GEN_5 = {RW0_rdata_0_6,RW0_rdata_0_5,RW0_rdata_0_4,RW0_rdata_0_3,RW0_rdata_0_2,RW0_rdata_0_1,
    RW0_rdata_0_0};
  wire [151:0] RW0_rdata_0 = {RW0_rdata_0_7,RW0_rdata_0_6,RW0_rdata_0_5,RW0_rdata_0_4,RW0_rdata_0_3,RW0_rdata_0_2,
    RW0_rdata_0_1,RW0_rdata_0_0};
  wire [37:0] _GEN_6 = {RW0_rdata_0_1,RW0_rdata_0_0};
  wire [56:0] _GEN_7 = {RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  wire [75:0] _GEN_8 = {RW0_rdata_0_3,RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  wire [94:0] _GEN_9 = {RW0_rdata_0_4,RW0_rdata_0_3,RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  wire [113:0] _GEN_10 = {RW0_rdata_0_5,RW0_rdata_0_4,RW0_rdata_0_3,RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  wire [132:0] _GEN_11 = {RW0_rdata_0_6,RW0_rdata_0_5,RW0_rdata_0_4,RW0_rdata_0_3,RW0_rdata_0_2,RW0_rdata_0_1,
    RW0_rdata_0_0};
  split_cc_dir_ext mem_0_0 (
    .RW0_addr(mem_0_0_RW0_addr),
    .RW0_clk(mem_0_0_RW0_clk),
    .RW0_wdata(mem_0_0_RW0_wdata),
    .RW0_rdata(mem_0_0_RW0_rdata),
    .RW0_en(mem_0_0_RW0_en),
    .RW0_wmode(mem_0_0_RW0_wmode),
    .RW0_wmask(mem_0_0_RW0_wmask)
  );
  split_cc_dir_ext mem_0_1 (
    .RW0_addr(mem_0_1_RW0_addr),
    .RW0_clk(mem_0_1_RW0_clk),
    .RW0_wdata(mem_0_1_RW0_wdata),
    .RW0_rdata(mem_0_1_RW0_rdata),
    .RW0_en(mem_0_1_RW0_en),
    .RW0_wmode(mem_0_1_RW0_wmode),
    .RW0_wmask(mem_0_1_RW0_wmask)
  );
  split_cc_dir_ext mem_0_2 (
    .RW0_addr(mem_0_2_RW0_addr),
    .RW0_clk(mem_0_2_RW0_clk),
    .RW0_wdata(mem_0_2_RW0_wdata),
    .RW0_rdata(mem_0_2_RW0_rdata),
    .RW0_en(mem_0_2_RW0_en),
    .RW0_wmode(mem_0_2_RW0_wmode),
    .RW0_wmask(mem_0_2_RW0_wmask)
  );
  split_cc_dir_ext mem_0_3 (
    .RW0_addr(mem_0_3_RW0_addr),
    .RW0_clk(mem_0_3_RW0_clk),
    .RW0_wdata(mem_0_3_RW0_wdata),
    .RW0_rdata(mem_0_3_RW0_rdata),
    .RW0_en(mem_0_3_RW0_en),
    .RW0_wmode(mem_0_3_RW0_wmode),
    .RW0_wmask(mem_0_3_RW0_wmask)
  );
  split_cc_dir_ext mem_0_4 (
    .RW0_addr(mem_0_4_RW0_addr),
    .RW0_clk(mem_0_4_RW0_clk),
    .RW0_wdata(mem_0_4_RW0_wdata),
    .RW0_rdata(mem_0_4_RW0_rdata),
    .RW0_en(mem_0_4_RW0_en),
    .RW0_wmode(mem_0_4_RW0_wmode),
    .RW0_wmask(mem_0_4_RW0_wmask)
  );
  split_cc_dir_ext mem_0_5 (
    .RW0_addr(mem_0_5_RW0_addr),
    .RW0_clk(mem_0_5_RW0_clk),
    .RW0_wdata(mem_0_5_RW0_wdata),
    .RW0_rdata(mem_0_5_RW0_rdata),
    .RW0_en(mem_0_5_RW0_en),
    .RW0_wmode(mem_0_5_RW0_wmode),
    .RW0_wmask(mem_0_5_RW0_wmask)
  );
  split_cc_dir_ext mem_0_6 (
    .RW0_addr(mem_0_6_RW0_addr),
    .RW0_clk(mem_0_6_RW0_clk),
    .RW0_wdata(mem_0_6_RW0_wdata),
    .RW0_rdata(mem_0_6_RW0_rdata),
    .RW0_en(mem_0_6_RW0_en),
    .RW0_wmode(mem_0_6_RW0_wmode),
    .RW0_wmask(mem_0_6_RW0_wmask)
  );
  split_cc_dir_ext mem_0_7 (
    .RW0_addr(mem_0_7_RW0_addr),
    .RW0_clk(mem_0_7_RW0_clk),
    .RW0_wdata(mem_0_7_RW0_wdata),
    .RW0_rdata(mem_0_7_RW0_rdata),
    .RW0_en(mem_0_7_RW0_en),
    .RW0_wmode(mem_0_7_RW0_wmode),
    .RW0_wmask(mem_0_7_RW0_wmask)
  );
  assign RW0_rdata = {RW0_rdata_0_7,_GEN_5};
  assign mem_0_0_RW0_addr = RW0_addr;
  assign mem_0_0_RW0_clk = RW0_clk;
  assign mem_0_0_RW0_wdata = RW0_wdata[18:0];
  assign mem_0_0_RW0_en = RW0_en;
  assign mem_0_0_RW0_wmode = RW0_wmode;
  assign mem_0_0_RW0_wmask = RW0_wmask[0];
  assign mem_0_1_RW0_addr = RW0_addr;
  assign mem_0_1_RW0_clk = RW0_clk;
  assign mem_0_1_RW0_wdata = RW0_wdata[37:19];
  assign mem_0_1_RW0_en = RW0_en;
  assign mem_0_1_RW0_wmode = RW0_wmode;
  assign mem_0_1_RW0_wmask = RW0_wmask[1];
  assign mem_0_2_RW0_addr = RW0_addr;
  assign mem_0_2_RW0_clk = RW0_clk;
  assign mem_0_2_RW0_wdata = RW0_wdata[56:38];
  assign mem_0_2_RW0_en = RW0_en;
  assign mem_0_2_RW0_wmode = RW0_wmode;
  assign mem_0_2_RW0_wmask = RW0_wmask[2];
  assign mem_0_3_RW0_addr = RW0_addr;
  assign mem_0_3_RW0_clk = RW0_clk;
  assign mem_0_3_RW0_wdata = RW0_wdata[75:57];
  assign mem_0_3_RW0_en = RW0_en;
  assign mem_0_3_RW0_wmode = RW0_wmode;
  assign mem_0_3_RW0_wmask = RW0_wmask[3];
  assign mem_0_4_RW0_addr = RW0_addr;
  assign mem_0_4_RW0_clk = RW0_clk;
  assign mem_0_4_RW0_wdata = RW0_wdata[94:76];
  assign mem_0_4_RW0_en = RW0_en;
  assign mem_0_4_RW0_wmode = RW0_wmode;
  assign mem_0_4_RW0_wmask = RW0_wmask[4];
  assign mem_0_5_RW0_addr = RW0_addr;
  assign mem_0_5_RW0_clk = RW0_clk;
  assign mem_0_5_RW0_wdata = RW0_wdata[113:95];
  assign mem_0_5_RW0_en = RW0_en;
  assign mem_0_5_RW0_wmode = RW0_wmode;
  assign mem_0_5_RW0_wmask = RW0_wmask[5];
  assign mem_0_6_RW0_addr = RW0_addr;
  assign mem_0_6_RW0_clk = RW0_clk;
  assign mem_0_6_RW0_wdata = RW0_wdata[132:114];
  assign mem_0_6_RW0_en = RW0_en;
  assign mem_0_6_RW0_wmode = RW0_wmode;
  assign mem_0_6_RW0_wmask = RW0_wmask[6];
  assign mem_0_7_RW0_addr = RW0_addr;
  assign mem_0_7_RW0_clk = RW0_clk;
  assign mem_0_7_RW0_wdata = RW0_wdata[151:133];
  assign mem_0_7_RW0_en = RW0_en;
  assign mem_0_7_RW0_wmode = RW0_wmode;
  assign mem_0_7_RW0_wmask = RW0_wmask[7];
endmodule
module cc_banks_0_ext(
  input  [13:0] RW0_addr,
  input         RW0_clk,
  input  [63:0] RW0_wdata,
  output [63:0] RW0_rdata,
  input         RW0_en,
  input         RW0_wmode
);
  wire [13:0] mem_0_0_RW0_addr;
  wire  mem_0_0_RW0_clk;
  wire [63:0] mem_0_0_RW0_wdata;
  wire [63:0] mem_0_0_RW0_rdata;
  wire  mem_0_0_RW0_en;
  wire  mem_0_0_RW0_wmode;
  wire [63:0] RW0_rdata_0_0 = mem_0_0_RW0_rdata;
  wire [63:0] RW0_rdata_0 = RW0_rdata_0_0;
  split_cc_banks_0_ext mem_0_0 (
    .RW0_addr(mem_0_0_RW0_addr),
    .RW0_clk(mem_0_0_RW0_clk),
    .RW0_wdata(mem_0_0_RW0_wdata),
    .RW0_rdata(mem_0_0_RW0_rdata),
    .RW0_en(mem_0_0_RW0_en),
    .RW0_wmode(mem_0_0_RW0_wmode)
  );
  assign RW0_rdata = mem_0_0_RW0_rdata;
  assign mem_0_0_RW0_addr = RW0_addr;
  assign mem_0_0_RW0_clk = RW0_clk;
  assign mem_0_0_RW0_wdata = RW0_wdata;
  assign mem_0_0_RW0_en = RW0_en;
  assign mem_0_0_RW0_wmode = RW0_wmode;
endmodule
module tag_array_ext(
  input  [5:0]  RW0_addr,
  input         RW0_clk,
  input  [87:0] RW0_wdata,
  output [87:0] RW0_rdata,
  input         RW0_en,
  input         RW0_wmode,
  input  [3:0]  RW0_wmask
);
  wire [5:0] mem_0_0_RW0_addr;
  wire  mem_0_0_RW0_clk;
  wire [21:0] mem_0_0_RW0_wdata;
  wire [21:0] mem_0_0_RW0_rdata;
  wire  mem_0_0_RW0_en;
  wire  mem_0_0_RW0_wmode;
  wire  mem_0_0_RW0_wmask;
  wire [5:0] mem_0_1_RW0_addr;
  wire  mem_0_1_RW0_clk;
  wire [21:0] mem_0_1_RW0_wdata;
  wire [21:0] mem_0_1_RW0_rdata;
  wire  mem_0_1_RW0_en;
  wire  mem_0_1_RW0_wmode;
  wire  mem_0_1_RW0_wmask;
  wire [5:0] mem_0_2_RW0_addr;
  wire  mem_0_2_RW0_clk;
  wire [21:0] mem_0_2_RW0_wdata;
  wire [21:0] mem_0_2_RW0_rdata;
  wire  mem_0_2_RW0_en;
  wire  mem_0_2_RW0_wmode;
  wire  mem_0_2_RW0_wmask;
  wire [5:0] mem_0_3_RW0_addr;
  wire  mem_0_3_RW0_clk;
  wire [21:0] mem_0_3_RW0_wdata;
  wire [21:0] mem_0_3_RW0_rdata;
  wire  mem_0_3_RW0_en;
  wire  mem_0_3_RW0_wmode;
  wire  mem_0_3_RW0_wmask;
  wire [21:0] RW0_rdata_0_0 = mem_0_0_RW0_rdata;
  wire [21:0] RW0_rdata_0_1 = mem_0_1_RW0_rdata;
  wire [21:0] RW0_rdata_0_2 = mem_0_2_RW0_rdata;
  wire [21:0] RW0_rdata_0_3 = mem_0_3_RW0_rdata;
  wire [43:0] _GEN_0 = {RW0_rdata_0_1,RW0_rdata_0_0};
  wire [65:0] _GEN_1 = {RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  wire [87:0] RW0_rdata_0 = {RW0_rdata_0_3,RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  wire [43:0] _GEN_2 = {RW0_rdata_0_1,RW0_rdata_0_0};
  wire [65:0] _GEN_3 = {RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  split_tag_array_ext mem_0_0 (
    .RW0_addr(mem_0_0_RW0_addr),
    .RW0_clk(mem_0_0_RW0_clk),
    .RW0_wdata(mem_0_0_RW0_wdata),
    .RW0_rdata(mem_0_0_RW0_rdata),
    .RW0_en(mem_0_0_RW0_en),
    .RW0_wmode(mem_0_0_RW0_wmode),
    .RW0_wmask(mem_0_0_RW0_wmask)
  );
  split_tag_array_ext mem_0_1 (
    .RW0_addr(mem_0_1_RW0_addr),
    .RW0_clk(mem_0_1_RW0_clk),
    .RW0_wdata(mem_0_1_RW0_wdata),
    .RW0_rdata(mem_0_1_RW0_rdata),
    .RW0_en(mem_0_1_RW0_en),
    .RW0_wmode(mem_0_1_RW0_wmode),
    .RW0_wmask(mem_0_1_RW0_wmask)
  );
  split_tag_array_ext mem_0_2 (
    .RW0_addr(mem_0_2_RW0_addr),
    .RW0_clk(mem_0_2_RW0_clk),
    .RW0_wdata(mem_0_2_RW0_wdata),
    .RW0_rdata(mem_0_2_RW0_rdata),
    .RW0_en(mem_0_2_RW0_en),
    .RW0_wmode(mem_0_2_RW0_wmode),
    .RW0_wmask(mem_0_2_RW0_wmask)
  );
  split_tag_array_ext mem_0_3 (
    .RW0_addr(mem_0_3_RW0_addr),
    .RW0_clk(mem_0_3_RW0_clk),
    .RW0_wdata(mem_0_3_RW0_wdata),
    .RW0_rdata(mem_0_3_RW0_rdata),
    .RW0_en(mem_0_3_RW0_en),
    .RW0_wmode(mem_0_3_RW0_wmode),
    .RW0_wmask(mem_0_3_RW0_wmask)
  );
  assign RW0_rdata = {RW0_rdata_0_3,_GEN_1};
  assign mem_0_0_RW0_addr = RW0_addr;
  assign mem_0_0_RW0_clk = RW0_clk;
  assign mem_0_0_RW0_wdata = RW0_wdata[21:0];
  assign mem_0_0_RW0_en = RW0_en;
  assign mem_0_0_RW0_wmode = RW0_wmode;
  assign mem_0_0_RW0_wmask = RW0_wmask[0];
  assign mem_0_1_RW0_addr = RW0_addr;
  assign mem_0_1_RW0_clk = RW0_clk;
  assign mem_0_1_RW0_wdata = RW0_wdata[43:22];
  assign mem_0_1_RW0_en = RW0_en;
  assign mem_0_1_RW0_wmode = RW0_wmode;
  assign mem_0_1_RW0_wmask = RW0_wmask[1];
  assign mem_0_2_RW0_addr = RW0_addr;
  assign mem_0_2_RW0_clk = RW0_clk;
  assign mem_0_2_RW0_wdata = RW0_wdata[65:44];
  assign mem_0_2_RW0_en = RW0_en;
  assign mem_0_2_RW0_wmode = RW0_wmode;
  assign mem_0_2_RW0_wmask = RW0_wmask[2];
  assign mem_0_3_RW0_addr = RW0_addr;
  assign mem_0_3_RW0_clk = RW0_clk;
  assign mem_0_3_RW0_wdata = RW0_wdata[87:66];
  assign mem_0_3_RW0_en = RW0_en;
  assign mem_0_3_RW0_wmode = RW0_wmode;
  assign mem_0_3_RW0_wmask = RW0_wmask[3];
endmodule
module array_0_0_ext(
  input  [8:0]  W0_addr,
  input         W0_clk,
  input  [63:0] W0_data,
  input         W0_en,
  input         W0_mask,
  input  [8:0]  R0_addr,
  input         R0_clk,
  output [63:0] R0_data,
  input         R0_en
);
  wire [8:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire [63:0] mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire  mem_0_0_W0_mask;
  wire [8:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire [63:0] mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [63:0] R0_data_0_0 = mem_0_0_R0_data;
  wire [63:0] R0_data_0 = R0_data_0_0;
  split_array_0_0_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .W0_mask(mem_0_0_W0_mask),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  assign R0_data = mem_0_0_R0_data;
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data;
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_W0_mask = W0_mask;
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
endmodule
module tag_array_0_ext(
  input  [5:0]  RW0_addr,
  input         RW0_clk,
  input  [79:0] RW0_wdata,
  output [79:0] RW0_rdata,
  input         RW0_en,
  input         RW0_wmode,
  input  [3:0]  RW0_wmask
);
  wire [5:0] mem_0_0_RW0_addr;
  wire  mem_0_0_RW0_clk;
  wire [19:0] mem_0_0_RW0_wdata;
  wire [19:0] mem_0_0_RW0_rdata;
  wire  mem_0_0_RW0_en;
  wire  mem_0_0_RW0_wmode;
  wire  mem_0_0_RW0_wmask;
  wire [5:0] mem_0_1_RW0_addr;
  wire  mem_0_1_RW0_clk;
  wire [19:0] mem_0_1_RW0_wdata;
  wire [19:0] mem_0_1_RW0_rdata;
  wire  mem_0_1_RW0_en;
  wire  mem_0_1_RW0_wmode;
  wire  mem_0_1_RW0_wmask;
  wire [5:0] mem_0_2_RW0_addr;
  wire  mem_0_2_RW0_clk;
  wire [19:0] mem_0_2_RW0_wdata;
  wire [19:0] mem_0_2_RW0_rdata;
  wire  mem_0_2_RW0_en;
  wire  mem_0_2_RW0_wmode;
  wire  mem_0_2_RW0_wmask;
  wire [5:0] mem_0_3_RW0_addr;
  wire  mem_0_3_RW0_clk;
  wire [19:0] mem_0_3_RW0_wdata;
  wire [19:0] mem_0_3_RW0_rdata;
  wire  mem_0_3_RW0_en;
  wire  mem_0_3_RW0_wmode;
  wire  mem_0_3_RW0_wmask;
  wire [19:0] RW0_rdata_0_0 = mem_0_0_RW0_rdata;
  wire [19:0] RW0_rdata_0_1 = mem_0_1_RW0_rdata;
  wire [19:0] RW0_rdata_0_2 = mem_0_2_RW0_rdata;
  wire [19:0] RW0_rdata_0_3 = mem_0_3_RW0_rdata;
  wire [39:0] _GEN_0 = {RW0_rdata_0_1,RW0_rdata_0_0};
  wire [59:0] _GEN_1 = {RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  wire [79:0] RW0_rdata_0 = {RW0_rdata_0_3,RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  wire [39:0] _GEN_2 = {RW0_rdata_0_1,RW0_rdata_0_0};
  wire [59:0] _GEN_3 = {RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
  split_tag_array_0_ext mem_0_0 (
    .RW0_addr(mem_0_0_RW0_addr),
    .RW0_clk(mem_0_0_RW0_clk),
    .RW0_wdata(mem_0_0_RW0_wdata),
    .RW0_rdata(mem_0_0_RW0_rdata),
    .RW0_en(mem_0_0_RW0_en),
    .RW0_wmode(mem_0_0_RW0_wmode),
    .RW0_wmask(mem_0_0_RW0_wmask)
  );
  split_tag_array_0_ext mem_0_1 (
    .RW0_addr(mem_0_1_RW0_addr),
    .RW0_clk(mem_0_1_RW0_clk),
    .RW0_wdata(mem_0_1_RW0_wdata),
    .RW0_rdata(mem_0_1_RW0_rdata),
    .RW0_en(mem_0_1_RW0_en),
    .RW0_wmode(mem_0_1_RW0_wmode),
    .RW0_wmask(mem_0_1_RW0_wmask)
  );
  split_tag_array_0_ext mem_0_2 (
    .RW0_addr(mem_0_2_RW0_addr),
    .RW0_clk(mem_0_2_RW0_clk),
    .RW0_wdata(mem_0_2_RW0_wdata),
    .RW0_rdata(mem_0_2_RW0_rdata),
    .RW0_en(mem_0_2_RW0_en),
    .RW0_wmode(mem_0_2_RW0_wmode),
    .RW0_wmask(mem_0_2_RW0_wmask)
  );
  split_tag_array_0_ext mem_0_3 (
    .RW0_addr(mem_0_3_RW0_addr),
    .RW0_clk(mem_0_3_RW0_clk),
    .RW0_wdata(mem_0_3_RW0_wdata),
    .RW0_rdata(mem_0_3_RW0_rdata),
    .RW0_en(mem_0_3_RW0_en),
    .RW0_wmode(mem_0_3_RW0_wmode),
    .RW0_wmask(mem_0_3_RW0_wmask)
  );
  assign RW0_rdata = {RW0_rdata_0_3,_GEN_1};
  assign mem_0_0_RW0_addr = RW0_addr;
  assign mem_0_0_RW0_clk = RW0_clk;
  assign mem_0_0_RW0_wdata = RW0_wdata[19:0];
  assign mem_0_0_RW0_en = RW0_en;
  assign mem_0_0_RW0_wmode = RW0_wmode;
  assign mem_0_0_RW0_wmask = RW0_wmask[0];
  assign mem_0_1_RW0_addr = RW0_addr;
  assign mem_0_1_RW0_clk = RW0_clk;
  assign mem_0_1_RW0_wdata = RW0_wdata[39:20];
  assign mem_0_1_RW0_en = RW0_en;
  assign mem_0_1_RW0_wmode = RW0_wmode;
  assign mem_0_1_RW0_wmask = RW0_wmask[1];
  assign mem_0_2_RW0_addr = RW0_addr;
  assign mem_0_2_RW0_clk = RW0_clk;
  assign mem_0_2_RW0_wdata = RW0_wdata[59:40];
  assign mem_0_2_RW0_en = RW0_en;
  assign mem_0_2_RW0_wmode = RW0_wmode;
  assign mem_0_2_RW0_wmask = RW0_wmask[2];
  assign mem_0_3_RW0_addr = RW0_addr;
  assign mem_0_3_RW0_clk = RW0_clk;
  assign mem_0_3_RW0_wdata = RW0_wdata[79:60];
  assign mem_0_3_RW0_en = RW0_en;
  assign mem_0_3_RW0_wmode = RW0_wmode;
  assign mem_0_3_RW0_wmask = RW0_wmask[3];
endmodule
module dataArrayWay_0_ext(
  input  [8:0]  RW0_addr,
  input         RW0_clk,
  input  [63:0] RW0_wdata,
  output [63:0] RW0_rdata,
  input         RW0_en,
  input         RW0_wmode
);
  wire [8:0] mem_0_0_RW0_addr;
  wire  mem_0_0_RW0_clk;
  wire [63:0] mem_0_0_RW0_wdata;
  wire [63:0] mem_0_0_RW0_rdata;
  wire  mem_0_0_RW0_en;
  wire  mem_0_0_RW0_wmode;
  wire [63:0] RW0_rdata_0_0 = mem_0_0_RW0_rdata;
  wire [63:0] RW0_rdata_0 = RW0_rdata_0_0;
  split_dataArrayWay_0_ext mem_0_0 (
    .RW0_addr(mem_0_0_RW0_addr),
    .RW0_clk(mem_0_0_RW0_clk),
    .RW0_wdata(mem_0_0_RW0_wdata),
    .RW0_rdata(mem_0_0_RW0_rdata),
    .RW0_en(mem_0_0_RW0_en),
    .RW0_wmode(mem_0_0_RW0_wmode)
  );
  assign RW0_rdata = mem_0_0_RW0_rdata;
  assign mem_0_0_RW0_addr = RW0_addr;
  assign mem_0_0_RW0_clk = RW0_clk;
  assign mem_0_0_RW0_wdata = RW0_wdata;
  assign mem_0_0_RW0_en = RW0_en;
  assign mem_0_0_RW0_wmode = RW0_wmode;
endmodule
module hi_us_ext(
  input  [6:0] W0_addr,
  input        W0_clk,
  input  [3:0] W0_data,
  input        W0_en,
  input  [3:0] W0_mask,
  input  [6:0] R0_addr,
  input        R0_clk,
  output [3:0] R0_data,
  input        R0_en
);
  wire [6:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire  mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire  mem_0_0_W0_mask;
  wire [6:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire  mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [6:0] mem_0_1_W0_addr;
  wire  mem_0_1_W0_clk;
  wire  mem_0_1_W0_data;
  wire  mem_0_1_W0_en;
  wire  mem_0_1_W0_mask;
  wire [6:0] mem_0_1_R0_addr;
  wire  mem_0_1_R0_clk;
  wire  mem_0_1_R0_data;
  wire  mem_0_1_R0_en;
  wire [6:0] mem_0_2_W0_addr;
  wire  mem_0_2_W0_clk;
  wire  mem_0_2_W0_data;
  wire  mem_0_2_W0_en;
  wire  mem_0_2_W0_mask;
  wire [6:0] mem_0_2_R0_addr;
  wire  mem_0_2_R0_clk;
  wire  mem_0_2_R0_data;
  wire  mem_0_2_R0_en;
  wire [6:0] mem_0_3_W0_addr;
  wire  mem_0_3_W0_clk;
  wire  mem_0_3_W0_data;
  wire  mem_0_3_W0_en;
  wire  mem_0_3_W0_mask;
  wire [6:0] mem_0_3_R0_addr;
  wire  mem_0_3_R0_clk;
  wire  mem_0_3_R0_data;
  wire  mem_0_3_R0_en;
  wire  R0_data_0_0 = mem_0_0_R0_data;
  wire  R0_data_0_1 = mem_0_1_R0_data;
  wire  R0_data_0_2 = mem_0_2_R0_data;
  wire  R0_data_0_3 = mem_0_3_R0_data;
  wire [1:0] _GEN_0 = {R0_data_0_1,R0_data_0_0};
  wire [2:0] _GEN_1 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [3:0] R0_data_0 = {R0_data_0_3,R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [1:0] _GEN_2 = {R0_data_0_1,R0_data_0_0};
  wire [2:0] _GEN_3 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  split_hi_us_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .W0_mask(mem_0_0_W0_mask),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  split_hi_us_ext mem_0_1 (
    .W0_addr(mem_0_1_W0_addr),
    .W0_clk(mem_0_1_W0_clk),
    .W0_data(mem_0_1_W0_data),
    .W0_en(mem_0_1_W0_en),
    .W0_mask(mem_0_1_W0_mask),
    .R0_addr(mem_0_1_R0_addr),
    .R0_clk(mem_0_1_R0_clk),
    .R0_data(mem_0_1_R0_data),
    .R0_en(mem_0_1_R0_en)
  );
  split_hi_us_ext mem_0_2 (
    .W0_addr(mem_0_2_W0_addr),
    .W0_clk(mem_0_2_W0_clk),
    .W0_data(mem_0_2_W0_data),
    .W0_en(mem_0_2_W0_en),
    .W0_mask(mem_0_2_W0_mask),
    .R0_addr(mem_0_2_R0_addr),
    .R0_clk(mem_0_2_R0_clk),
    .R0_data(mem_0_2_R0_data),
    .R0_en(mem_0_2_R0_en)
  );
  split_hi_us_ext mem_0_3 (
    .W0_addr(mem_0_3_W0_addr),
    .W0_clk(mem_0_3_W0_clk),
    .W0_data(mem_0_3_W0_data),
    .W0_en(mem_0_3_W0_en),
    .W0_mask(mem_0_3_W0_mask),
    .R0_addr(mem_0_3_R0_addr),
    .R0_clk(mem_0_3_R0_clk),
    .R0_data(mem_0_3_R0_data),
    .R0_en(mem_0_3_R0_en)
  );
  assign R0_data = {R0_data_0_3,_GEN_1};
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data[0];
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_W0_mask = W0_mask[0];
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
  assign mem_0_1_W0_addr = W0_addr;
  assign mem_0_1_W0_clk = W0_clk;
  assign mem_0_1_W0_data = W0_data[1];
  assign mem_0_1_W0_en = W0_en;
  assign mem_0_1_W0_mask = W0_mask[1];
  assign mem_0_1_R0_addr = R0_addr;
  assign mem_0_1_R0_clk = R0_clk;
  assign mem_0_1_R0_en = R0_en;
  assign mem_0_2_W0_addr = W0_addr;
  assign mem_0_2_W0_clk = W0_clk;
  assign mem_0_2_W0_data = W0_data[2];
  assign mem_0_2_W0_en = W0_en;
  assign mem_0_2_W0_mask = W0_mask[2];
  assign mem_0_2_R0_addr = R0_addr;
  assign mem_0_2_R0_clk = R0_clk;
  assign mem_0_2_R0_en = R0_en;
  assign mem_0_3_W0_addr = W0_addr;
  assign mem_0_3_W0_clk = W0_clk;
  assign mem_0_3_W0_data = W0_data[3];
  assign mem_0_3_W0_en = W0_en;
  assign mem_0_3_W0_mask = W0_mask[3];
  assign mem_0_3_R0_addr = R0_addr;
  assign mem_0_3_R0_clk = R0_clk;
  assign mem_0_3_R0_en = R0_en;
endmodule
module table_ext(
  input  [6:0]  W0_addr,
  input         W0_clk,
  input  [43:0] W0_data,
  input         W0_en,
  input  [3:0]  W0_mask,
  input  [6:0]  R0_addr,
  input         R0_clk,
  output [43:0] R0_data,
  input         R0_en
);
  wire [6:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire [10:0] mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire  mem_0_0_W0_mask;
  wire [6:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire [10:0] mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [6:0] mem_0_1_W0_addr;
  wire  mem_0_1_W0_clk;
  wire [10:0] mem_0_1_W0_data;
  wire  mem_0_1_W0_en;
  wire  mem_0_1_W0_mask;
  wire [6:0] mem_0_1_R0_addr;
  wire  mem_0_1_R0_clk;
  wire [10:0] mem_0_1_R0_data;
  wire  mem_0_1_R0_en;
  wire [6:0] mem_0_2_W0_addr;
  wire  mem_0_2_W0_clk;
  wire [10:0] mem_0_2_W0_data;
  wire  mem_0_2_W0_en;
  wire  mem_0_2_W0_mask;
  wire [6:0] mem_0_2_R0_addr;
  wire  mem_0_2_R0_clk;
  wire [10:0] mem_0_2_R0_data;
  wire  mem_0_2_R0_en;
  wire [6:0] mem_0_3_W0_addr;
  wire  mem_0_3_W0_clk;
  wire [10:0] mem_0_3_W0_data;
  wire  mem_0_3_W0_en;
  wire  mem_0_3_W0_mask;
  wire [6:0] mem_0_3_R0_addr;
  wire  mem_0_3_R0_clk;
  wire [10:0] mem_0_3_R0_data;
  wire  mem_0_3_R0_en;
  wire [10:0] R0_data_0_0 = mem_0_0_R0_data;
  wire [10:0] R0_data_0_1 = mem_0_1_R0_data;
  wire [10:0] R0_data_0_2 = mem_0_2_R0_data;
  wire [10:0] R0_data_0_3 = mem_0_3_R0_data;
  wire [21:0] _GEN_0 = {R0_data_0_1,R0_data_0_0};
  wire [32:0] _GEN_1 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [43:0] R0_data_0 = {R0_data_0_3,R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [21:0] _GEN_2 = {R0_data_0_1,R0_data_0_0};
  wire [32:0] _GEN_3 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  split_table_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .W0_mask(mem_0_0_W0_mask),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  split_table_ext mem_0_1 (
    .W0_addr(mem_0_1_W0_addr),
    .W0_clk(mem_0_1_W0_clk),
    .W0_data(mem_0_1_W0_data),
    .W0_en(mem_0_1_W0_en),
    .W0_mask(mem_0_1_W0_mask),
    .R0_addr(mem_0_1_R0_addr),
    .R0_clk(mem_0_1_R0_clk),
    .R0_data(mem_0_1_R0_data),
    .R0_en(mem_0_1_R0_en)
  );
  split_table_ext mem_0_2 (
    .W0_addr(mem_0_2_W0_addr),
    .W0_clk(mem_0_2_W0_clk),
    .W0_data(mem_0_2_W0_data),
    .W0_en(mem_0_2_W0_en),
    .W0_mask(mem_0_2_W0_mask),
    .R0_addr(mem_0_2_R0_addr),
    .R0_clk(mem_0_2_R0_clk),
    .R0_data(mem_0_2_R0_data),
    .R0_en(mem_0_2_R0_en)
  );
  split_table_ext mem_0_3 (
    .W0_addr(mem_0_3_W0_addr),
    .W0_clk(mem_0_3_W0_clk),
    .W0_data(mem_0_3_W0_data),
    .W0_en(mem_0_3_W0_en),
    .W0_mask(mem_0_3_W0_mask),
    .R0_addr(mem_0_3_R0_addr),
    .R0_clk(mem_0_3_R0_clk),
    .R0_data(mem_0_3_R0_data),
    .R0_en(mem_0_3_R0_en)
  );
  assign R0_data = {R0_data_0_3,_GEN_1};
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data[10:0];
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_W0_mask = W0_mask[0];
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
  assign mem_0_1_W0_addr = W0_addr;
  assign mem_0_1_W0_clk = W0_clk;
  assign mem_0_1_W0_data = W0_data[21:11];
  assign mem_0_1_W0_en = W0_en;
  assign mem_0_1_W0_mask = W0_mask[1];
  assign mem_0_1_R0_addr = R0_addr;
  assign mem_0_1_R0_clk = R0_clk;
  assign mem_0_1_R0_en = R0_en;
  assign mem_0_2_W0_addr = W0_addr;
  assign mem_0_2_W0_clk = W0_clk;
  assign mem_0_2_W0_data = W0_data[32:22];
  assign mem_0_2_W0_en = W0_en;
  assign mem_0_2_W0_mask = W0_mask[2];
  assign mem_0_2_R0_addr = R0_addr;
  assign mem_0_2_R0_clk = R0_clk;
  assign mem_0_2_R0_en = R0_en;
  assign mem_0_3_W0_addr = W0_addr;
  assign mem_0_3_W0_clk = W0_clk;
  assign mem_0_3_W0_data = W0_data[43:33];
  assign mem_0_3_W0_en = W0_en;
  assign mem_0_3_W0_mask = W0_mask[3];
  assign mem_0_3_R0_addr = R0_addr;
  assign mem_0_3_R0_clk = R0_clk;
  assign mem_0_3_R0_en = R0_en;
endmodule
module hi_us_0_ext(
  input  [7:0] W0_addr,
  input        W0_clk,
  input  [3:0] W0_data,
  input        W0_en,
  input  [3:0] W0_mask,
  input  [7:0] R0_addr,
  input        R0_clk,
  output [3:0] R0_data,
  input        R0_en
);
  wire [7:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire  mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire  mem_0_0_W0_mask;
  wire [7:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire  mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [7:0] mem_0_1_W0_addr;
  wire  mem_0_1_W0_clk;
  wire  mem_0_1_W0_data;
  wire  mem_0_1_W0_en;
  wire  mem_0_1_W0_mask;
  wire [7:0] mem_0_1_R0_addr;
  wire  mem_0_1_R0_clk;
  wire  mem_0_1_R0_data;
  wire  mem_0_1_R0_en;
  wire [7:0] mem_0_2_W0_addr;
  wire  mem_0_2_W0_clk;
  wire  mem_0_2_W0_data;
  wire  mem_0_2_W0_en;
  wire  mem_0_2_W0_mask;
  wire [7:0] mem_0_2_R0_addr;
  wire  mem_0_2_R0_clk;
  wire  mem_0_2_R0_data;
  wire  mem_0_2_R0_en;
  wire [7:0] mem_0_3_W0_addr;
  wire  mem_0_3_W0_clk;
  wire  mem_0_3_W0_data;
  wire  mem_0_3_W0_en;
  wire  mem_0_3_W0_mask;
  wire [7:0] mem_0_3_R0_addr;
  wire  mem_0_3_R0_clk;
  wire  mem_0_3_R0_data;
  wire  mem_0_3_R0_en;
  wire  R0_data_0_0 = mem_0_0_R0_data;
  wire  R0_data_0_1 = mem_0_1_R0_data;
  wire  R0_data_0_2 = mem_0_2_R0_data;
  wire  R0_data_0_3 = mem_0_3_R0_data;
  wire [1:0] _GEN_0 = {R0_data_0_1,R0_data_0_0};
  wire [2:0] _GEN_1 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [3:0] R0_data_0 = {R0_data_0_3,R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [1:0] _GEN_2 = {R0_data_0_1,R0_data_0_0};
  wire [2:0] _GEN_3 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  split_hi_us_0_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .W0_mask(mem_0_0_W0_mask),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  split_hi_us_0_ext mem_0_1 (
    .W0_addr(mem_0_1_W0_addr),
    .W0_clk(mem_0_1_W0_clk),
    .W0_data(mem_0_1_W0_data),
    .W0_en(mem_0_1_W0_en),
    .W0_mask(mem_0_1_W0_mask),
    .R0_addr(mem_0_1_R0_addr),
    .R0_clk(mem_0_1_R0_clk),
    .R0_data(mem_0_1_R0_data),
    .R0_en(mem_0_1_R0_en)
  );
  split_hi_us_0_ext mem_0_2 (
    .W0_addr(mem_0_2_W0_addr),
    .W0_clk(mem_0_2_W0_clk),
    .W0_data(mem_0_2_W0_data),
    .W0_en(mem_0_2_W0_en),
    .W0_mask(mem_0_2_W0_mask),
    .R0_addr(mem_0_2_R0_addr),
    .R0_clk(mem_0_2_R0_clk),
    .R0_data(mem_0_2_R0_data),
    .R0_en(mem_0_2_R0_en)
  );
  split_hi_us_0_ext mem_0_3 (
    .W0_addr(mem_0_3_W0_addr),
    .W0_clk(mem_0_3_W0_clk),
    .W0_data(mem_0_3_W0_data),
    .W0_en(mem_0_3_W0_en),
    .W0_mask(mem_0_3_W0_mask),
    .R0_addr(mem_0_3_R0_addr),
    .R0_clk(mem_0_3_R0_clk),
    .R0_data(mem_0_3_R0_data),
    .R0_en(mem_0_3_R0_en)
  );
  assign R0_data = {R0_data_0_3,_GEN_1};
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data[0];
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_W0_mask = W0_mask[0];
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
  assign mem_0_1_W0_addr = W0_addr;
  assign mem_0_1_W0_clk = W0_clk;
  assign mem_0_1_W0_data = W0_data[1];
  assign mem_0_1_W0_en = W0_en;
  assign mem_0_1_W0_mask = W0_mask[1];
  assign mem_0_1_R0_addr = R0_addr;
  assign mem_0_1_R0_clk = R0_clk;
  assign mem_0_1_R0_en = R0_en;
  assign mem_0_2_W0_addr = W0_addr;
  assign mem_0_2_W0_clk = W0_clk;
  assign mem_0_2_W0_data = W0_data[2];
  assign mem_0_2_W0_en = W0_en;
  assign mem_0_2_W0_mask = W0_mask[2];
  assign mem_0_2_R0_addr = R0_addr;
  assign mem_0_2_R0_clk = R0_clk;
  assign mem_0_2_R0_en = R0_en;
  assign mem_0_3_W0_addr = W0_addr;
  assign mem_0_3_W0_clk = W0_clk;
  assign mem_0_3_W0_data = W0_data[3];
  assign mem_0_3_W0_en = W0_en;
  assign mem_0_3_W0_mask = W0_mask[3];
  assign mem_0_3_R0_addr = R0_addr;
  assign mem_0_3_R0_clk = R0_clk;
  assign mem_0_3_R0_en = R0_en;
endmodule
module table_0_ext(
  input  [7:0]  W0_addr,
  input         W0_clk,
  input  [47:0] W0_data,
  input         W0_en,
  input  [3:0]  W0_mask,
  input  [7:0]  R0_addr,
  input         R0_clk,
  output [47:0] R0_data,
  input         R0_en
);
  wire [7:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire [11:0] mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire  mem_0_0_W0_mask;
  wire [7:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire [11:0] mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [7:0] mem_0_1_W0_addr;
  wire  mem_0_1_W0_clk;
  wire [11:0] mem_0_1_W0_data;
  wire  mem_0_1_W0_en;
  wire  mem_0_1_W0_mask;
  wire [7:0] mem_0_1_R0_addr;
  wire  mem_0_1_R0_clk;
  wire [11:0] mem_0_1_R0_data;
  wire  mem_0_1_R0_en;
  wire [7:0] mem_0_2_W0_addr;
  wire  mem_0_2_W0_clk;
  wire [11:0] mem_0_2_W0_data;
  wire  mem_0_2_W0_en;
  wire  mem_0_2_W0_mask;
  wire [7:0] mem_0_2_R0_addr;
  wire  mem_0_2_R0_clk;
  wire [11:0] mem_0_2_R0_data;
  wire  mem_0_2_R0_en;
  wire [7:0] mem_0_3_W0_addr;
  wire  mem_0_3_W0_clk;
  wire [11:0] mem_0_3_W0_data;
  wire  mem_0_3_W0_en;
  wire  mem_0_3_W0_mask;
  wire [7:0] mem_0_3_R0_addr;
  wire  mem_0_3_R0_clk;
  wire [11:0] mem_0_3_R0_data;
  wire  mem_0_3_R0_en;
  wire [11:0] R0_data_0_0 = mem_0_0_R0_data;
  wire [11:0] R0_data_0_1 = mem_0_1_R0_data;
  wire [11:0] R0_data_0_2 = mem_0_2_R0_data;
  wire [11:0] R0_data_0_3 = mem_0_3_R0_data;
  wire [23:0] _GEN_0 = {R0_data_0_1,R0_data_0_0};
  wire [35:0] _GEN_1 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [47:0] R0_data_0 = {R0_data_0_3,R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [23:0] _GEN_2 = {R0_data_0_1,R0_data_0_0};
  wire [35:0] _GEN_3 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  split_table_0_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .W0_mask(mem_0_0_W0_mask),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  split_table_0_ext mem_0_1 (
    .W0_addr(mem_0_1_W0_addr),
    .W0_clk(mem_0_1_W0_clk),
    .W0_data(mem_0_1_W0_data),
    .W0_en(mem_0_1_W0_en),
    .W0_mask(mem_0_1_W0_mask),
    .R0_addr(mem_0_1_R0_addr),
    .R0_clk(mem_0_1_R0_clk),
    .R0_data(mem_0_1_R0_data),
    .R0_en(mem_0_1_R0_en)
  );
  split_table_0_ext mem_0_2 (
    .W0_addr(mem_0_2_W0_addr),
    .W0_clk(mem_0_2_W0_clk),
    .W0_data(mem_0_2_W0_data),
    .W0_en(mem_0_2_W0_en),
    .W0_mask(mem_0_2_W0_mask),
    .R0_addr(mem_0_2_R0_addr),
    .R0_clk(mem_0_2_R0_clk),
    .R0_data(mem_0_2_R0_data),
    .R0_en(mem_0_2_R0_en)
  );
  split_table_0_ext mem_0_3 (
    .W0_addr(mem_0_3_W0_addr),
    .W0_clk(mem_0_3_W0_clk),
    .W0_data(mem_0_3_W0_data),
    .W0_en(mem_0_3_W0_en),
    .W0_mask(mem_0_3_W0_mask),
    .R0_addr(mem_0_3_R0_addr),
    .R0_clk(mem_0_3_R0_clk),
    .R0_data(mem_0_3_R0_data),
    .R0_en(mem_0_3_R0_en)
  );
  assign R0_data = {R0_data_0_3,_GEN_1};
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data[11:0];
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_W0_mask = W0_mask[0];
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
  assign mem_0_1_W0_addr = W0_addr;
  assign mem_0_1_W0_clk = W0_clk;
  assign mem_0_1_W0_data = W0_data[23:12];
  assign mem_0_1_W0_en = W0_en;
  assign mem_0_1_W0_mask = W0_mask[1];
  assign mem_0_1_R0_addr = R0_addr;
  assign mem_0_1_R0_clk = R0_clk;
  assign mem_0_1_R0_en = R0_en;
  assign mem_0_2_W0_addr = W0_addr;
  assign mem_0_2_W0_clk = W0_clk;
  assign mem_0_2_W0_data = W0_data[35:24];
  assign mem_0_2_W0_en = W0_en;
  assign mem_0_2_W0_mask = W0_mask[2];
  assign mem_0_2_R0_addr = R0_addr;
  assign mem_0_2_R0_clk = R0_clk;
  assign mem_0_2_R0_en = R0_en;
  assign mem_0_3_W0_addr = W0_addr;
  assign mem_0_3_W0_clk = W0_clk;
  assign mem_0_3_W0_data = W0_data[47:36];
  assign mem_0_3_W0_en = W0_en;
  assign mem_0_3_W0_mask = W0_mask[3];
  assign mem_0_3_R0_addr = R0_addr;
  assign mem_0_3_R0_clk = R0_clk;
  assign mem_0_3_R0_en = R0_en;
endmodule
module table_1_ext(
  input  [6:0]  W0_addr,
  input         W0_clk,
  input  [51:0] W0_data,
  input         W0_en,
  input  [3:0]  W0_mask,
  input  [6:0]  R0_addr,
  input         R0_clk,
  output [51:0] R0_data,
  input         R0_en
);
  wire [6:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire [12:0] mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire  mem_0_0_W0_mask;
  wire [6:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire [12:0] mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [6:0] mem_0_1_W0_addr;
  wire  mem_0_1_W0_clk;
  wire [12:0] mem_0_1_W0_data;
  wire  mem_0_1_W0_en;
  wire  mem_0_1_W0_mask;
  wire [6:0] mem_0_1_R0_addr;
  wire  mem_0_1_R0_clk;
  wire [12:0] mem_0_1_R0_data;
  wire  mem_0_1_R0_en;
  wire [6:0] mem_0_2_W0_addr;
  wire  mem_0_2_W0_clk;
  wire [12:0] mem_0_2_W0_data;
  wire  mem_0_2_W0_en;
  wire  mem_0_2_W0_mask;
  wire [6:0] mem_0_2_R0_addr;
  wire  mem_0_2_R0_clk;
  wire [12:0] mem_0_2_R0_data;
  wire  mem_0_2_R0_en;
  wire [6:0] mem_0_3_W0_addr;
  wire  mem_0_3_W0_clk;
  wire [12:0] mem_0_3_W0_data;
  wire  mem_0_3_W0_en;
  wire  mem_0_3_W0_mask;
  wire [6:0] mem_0_3_R0_addr;
  wire  mem_0_3_R0_clk;
  wire [12:0] mem_0_3_R0_data;
  wire  mem_0_3_R0_en;
  wire [12:0] R0_data_0_0 = mem_0_0_R0_data;
  wire [12:0] R0_data_0_1 = mem_0_1_R0_data;
  wire [12:0] R0_data_0_2 = mem_0_2_R0_data;
  wire [12:0] R0_data_0_3 = mem_0_3_R0_data;
  wire [25:0] _GEN_0 = {R0_data_0_1,R0_data_0_0};
  wire [38:0] _GEN_1 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [51:0] R0_data_0 = {R0_data_0_3,R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [25:0] _GEN_2 = {R0_data_0_1,R0_data_0_0};
  wire [38:0] _GEN_3 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  split_table_1_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .W0_mask(mem_0_0_W0_mask),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  split_table_1_ext mem_0_1 (
    .W0_addr(mem_0_1_W0_addr),
    .W0_clk(mem_0_1_W0_clk),
    .W0_data(mem_0_1_W0_data),
    .W0_en(mem_0_1_W0_en),
    .W0_mask(mem_0_1_W0_mask),
    .R0_addr(mem_0_1_R0_addr),
    .R0_clk(mem_0_1_R0_clk),
    .R0_data(mem_0_1_R0_data),
    .R0_en(mem_0_1_R0_en)
  );
  split_table_1_ext mem_0_2 (
    .W0_addr(mem_0_2_W0_addr),
    .W0_clk(mem_0_2_W0_clk),
    .W0_data(mem_0_2_W0_data),
    .W0_en(mem_0_2_W0_en),
    .W0_mask(mem_0_2_W0_mask),
    .R0_addr(mem_0_2_R0_addr),
    .R0_clk(mem_0_2_R0_clk),
    .R0_data(mem_0_2_R0_data),
    .R0_en(mem_0_2_R0_en)
  );
  split_table_1_ext mem_0_3 (
    .W0_addr(mem_0_3_W0_addr),
    .W0_clk(mem_0_3_W0_clk),
    .W0_data(mem_0_3_W0_data),
    .W0_en(mem_0_3_W0_en),
    .W0_mask(mem_0_3_W0_mask),
    .R0_addr(mem_0_3_R0_addr),
    .R0_clk(mem_0_3_R0_clk),
    .R0_data(mem_0_3_R0_data),
    .R0_en(mem_0_3_R0_en)
  );
  assign R0_data = {R0_data_0_3,_GEN_1};
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data[12:0];
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_W0_mask = W0_mask[0];
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
  assign mem_0_1_W0_addr = W0_addr;
  assign mem_0_1_W0_clk = W0_clk;
  assign mem_0_1_W0_data = W0_data[25:13];
  assign mem_0_1_W0_en = W0_en;
  assign mem_0_1_W0_mask = W0_mask[1];
  assign mem_0_1_R0_addr = R0_addr;
  assign mem_0_1_R0_clk = R0_clk;
  assign mem_0_1_R0_en = R0_en;
  assign mem_0_2_W0_addr = W0_addr;
  assign mem_0_2_W0_clk = W0_clk;
  assign mem_0_2_W0_data = W0_data[38:26];
  assign mem_0_2_W0_en = W0_en;
  assign mem_0_2_W0_mask = W0_mask[2];
  assign mem_0_2_R0_addr = R0_addr;
  assign mem_0_2_R0_clk = R0_clk;
  assign mem_0_2_R0_en = R0_en;
  assign mem_0_3_W0_addr = W0_addr;
  assign mem_0_3_W0_clk = W0_clk;
  assign mem_0_3_W0_data = W0_data[51:39];
  assign mem_0_3_W0_en = W0_en;
  assign mem_0_3_W0_mask = W0_mask[3];
  assign mem_0_3_R0_addr = R0_addr;
  assign mem_0_3_R0_clk = R0_clk;
  assign mem_0_3_R0_en = R0_en;
endmodule
module meta_0_ext(
  input  [6:0]   W0_addr,
  input          W0_clk,
  input  [123:0] W0_data,
  input          W0_en,
  input  [3:0]   W0_mask,
  input  [6:0]   R0_addr,
  input          R0_clk,
  output [123:0] R0_data,
  input          R0_en
);
  wire [6:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire [30:0] mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire  mem_0_0_W0_mask;
  wire [6:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire [30:0] mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [6:0] mem_0_1_W0_addr;
  wire  mem_0_1_W0_clk;
  wire [30:0] mem_0_1_W0_data;
  wire  mem_0_1_W0_en;
  wire  mem_0_1_W0_mask;
  wire [6:0] mem_0_1_R0_addr;
  wire  mem_0_1_R0_clk;
  wire [30:0] mem_0_1_R0_data;
  wire  mem_0_1_R0_en;
  wire [6:0] mem_0_2_W0_addr;
  wire  mem_0_2_W0_clk;
  wire [30:0] mem_0_2_W0_data;
  wire  mem_0_2_W0_en;
  wire  mem_0_2_W0_mask;
  wire [6:0] mem_0_2_R0_addr;
  wire  mem_0_2_R0_clk;
  wire [30:0] mem_0_2_R0_data;
  wire  mem_0_2_R0_en;
  wire [6:0] mem_0_3_W0_addr;
  wire  mem_0_3_W0_clk;
  wire [30:0] mem_0_3_W0_data;
  wire  mem_0_3_W0_en;
  wire  mem_0_3_W0_mask;
  wire [6:0] mem_0_3_R0_addr;
  wire  mem_0_3_R0_clk;
  wire [30:0] mem_0_3_R0_data;
  wire  mem_0_3_R0_en;
  wire [30:0] R0_data_0_0 = mem_0_0_R0_data;
  wire [30:0] R0_data_0_1 = mem_0_1_R0_data;
  wire [30:0] R0_data_0_2 = mem_0_2_R0_data;
  wire [30:0] R0_data_0_3 = mem_0_3_R0_data;
  wire [61:0] _GEN_0 = {R0_data_0_1,R0_data_0_0};
  wire [92:0] _GEN_1 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [123:0] R0_data_0 = {R0_data_0_3,R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [61:0] _GEN_2 = {R0_data_0_1,R0_data_0_0};
  wire [92:0] _GEN_3 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  split_meta_0_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .W0_mask(mem_0_0_W0_mask),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  split_meta_0_ext mem_0_1 (
    .W0_addr(mem_0_1_W0_addr),
    .W0_clk(mem_0_1_W0_clk),
    .W0_data(mem_0_1_W0_data),
    .W0_en(mem_0_1_W0_en),
    .W0_mask(mem_0_1_W0_mask),
    .R0_addr(mem_0_1_R0_addr),
    .R0_clk(mem_0_1_R0_clk),
    .R0_data(mem_0_1_R0_data),
    .R0_en(mem_0_1_R0_en)
  );
  split_meta_0_ext mem_0_2 (
    .W0_addr(mem_0_2_W0_addr),
    .W0_clk(mem_0_2_W0_clk),
    .W0_data(mem_0_2_W0_data),
    .W0_en(mem_0_2_W0_en),
    .W0_mask(mem_0_2_W0_mask),
    .R0_addr(mem_0_2_R0_addr),
    .R0_clk(mem_0_2_R0_clk),
    .R0_data(mem_0_2_R0_data),
    .R0_en(mem_0_2_R0_en)
  );
  split_meta_0_ext mem_0_3 (
    .W0_addr(mem_0_3_W0_addr),
    .W0_clk(mem_0_3_W0_clk),
    .W0_data(mem_0_3_W0_data),
    .W0_en(mem_0_3_W0_en),
    .W0_mask(mem_0_3_W0_mask),
    .R0_addr(mem_0_3_R0_addr),
    .R0_clk(mem_0_3_R0_clk),
    .R0_data(mem_0_3_R0_data),
    .R0_en(mem_0_3_R0_en)
  );
  assign R0_data = {R0_data_0_3,_GEN_1};
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data[30:0];
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_W0_mask = W0_mask[0];
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
  assign mem_0_1_W0_addr = W0_addr;
  assign mem_0_1_W0_clk = W0_clk;
  assign mem_0_1_W0_data = W0_data[61:31];
  assign mem_0_1_W0_en = W0_en;
  assign mem_0_1_W0_mask = W0_mask[1];
  assign mem_0_1_R0_addr = R0_addr;
  assign mem_0_1_R0_clk = R0_clk;
  assign mem_0_1_R0_en = R0_en;
  assign mem_0_2_W0_addr = W0_addr;
  assign mem_0_2_W0_clk = W0_clk;
  assign mem_0_2_W0_data = W0_data[92:62];
  assign mem_0_2_W0_en = W0_en;
  assign mem_0_2_W0_mask = W0_mask[2];
  assign mem_0_2_R0_addr = R0_addr;
  assign mem_0_2_R0_clk = R0_clk;
  assign mem_0_2_R0_en = R0_en;
  assign mem_0_3_W0_addr = W0_addr;
  assign mem_0_3_W0_clk = W0_clk;
  assign mem_0_3_W0_data = W0_data[123:93];
  assign mem_0_3_W0_en = W0_en;
  assign mem_0_3_W0_mask = W0_mask[3];
  assign mem_0_3_R0_addr = R0_addr;
  assign mem_0_3_R0_clk = R0_clk;
  assign mem_0_3_R0_en = R0_en;
endmodule
module btb_0_ext(
  input  [6:0]  W0_addr,
  input         W0_clk,
  input  [55:0] W0_data,
  input         W0_en,
  input  [3:0]  W0_mask,
  input  [6:0]  R0_addr,
  input         R0_clk,
  output [55:0] R0_data,
  input         R0_en
);
  wire [6:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire [13:0] mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire  mem_0_0_W0_mask;
  wire [6:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire [13:0] mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [6:0] mem_0_1_W0_addr;
  wire  mem_0_1_W0_clk;
  wire [13:0] mem_0_1_W0_data;
  wire  mem_0_1_W0_en;
  wire  mem_0_1_W0_mask;
  wire [6:0] mem_0_1_R0_addr;
  wire  mem_0_1_R0_clk;
  wire [13:0] mem_0_1_R0_data;
  wire  mem_0_1_R0_en;
  wire [6:0] mem_0_2_W0_addr;
  wire  mem_0_2_W0_clk;
  wire [13:0] mem_0_2_W0_data;
  wire  mem_0_2_W0_en;
  wire  mem_0_2_W0_mask;
  wire [6:0] mem_0_2_R0_addr;
  wire  mem_0_2_R0_clk;
  wire [13:0] mem_0_2_R0_data;
  wire  mem_0_2_R0_en;
  wire [6:0] mem_0_3_W0_addr;
  wire  mem_0_3_W0_clk;
  wire [13:0] mem_0_3_W0_data;
  wire  mem_0_3_W0_en;
  wire  mem_0_3_W0_mask;
  wire [6:0] mem_0_3_R0_addr;
  wire  mem_0_3_R0_clk;
  wire [13:0] mem_0_3_R0_data;
  wire  mem_0_3_R0_en;
  wire [13:0] R0_data_0_0 = mem_0_0_R0_data;
  wire [13:0] R0_data_0_1 = mem_0_1_R0_data;
  wire [13:0] R0_data_0_2 = mem_0_2_R0_data;
  wire [13:0] R0_data_0_3 = mem_0_3_R0_data;
  wire [27:0] _GEN_0 = {R0_data_0_1,R0_data_0_0};
  wire [41:0] _GEN_1 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [55:0] R0_data_0 = {R0_data_0_3,R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [27:0] _GEN_2 = {R0_data_0_1,R0_data_0_0};
  wire [41:0] _GEN_3 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  split_btb_0_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .W0_mask(mem_0_0_W0_mask),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  split_btb_0_ext mem_0_1 (
    .W0_addr(mem_0_1_W0_addr),
    .W0_clk(mem_0_1_W0_clk),
    .W0_data(mem_0_1_W0_data),
    .W0_en(mem_0_1_W0_en),
    .W0_mask(mem_0_1_W0_mask),
    .R0_addr(mem_0_1_R0_addr),
    .R0_clk(mem_0_1_R0_clk),
    .R0_data(mem_0_1_R0_data),
    .R0_en(mem_0_1_R0_en)
  );
  split_btb_0_ext mem_0_2 (
    .W0_addr(mem_0_2_W0_addr),
    .W0_clk(mem_0_2_W0_clk),
    .W0_data(mem_0_2_W0_data),
    .W0_en(mem_0_2_W0_en),
    .W0_mask(mem_0_2_W0_mask),
    .R0_addr(mem_0_2_R0_addr),
    .R0_clk(mem_0_2_R0_clk),
    .R0_data(mem_0_2_R0_data),
    .R0_en(mem_0_2_R0_en)
  );
  split_btb_0_ext mem_0_3 (
    .W0_addr(mem_0_3_W0_addr),
    .W0_clk(mem_0_3_W0_clk),
    .W0_data(mem_0_3_W0_data),
    .W0_en(mem_0_3_W0_en),
    .W0_mask(mem_0_3_W0_mask),
    .R0_addr(mem_0_3_R0_addr),
    .R0_clk(mem_0_3_R0_clk),
    .R0_data(mem_0_3_R0_data),
    .R0_en(mem_0_3_R0_en)
  );
  assign R0_data = {R0_data_0_3,_GEN_1};
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data[13:0];
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_W0_mask = W0_mask[0];
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
  assign mem_0_1_W0_addr = W0_addr;
  assign mem_0_1_W0_clk = W0_clk;
  assign mem_0_1_W0_data = W0_data[27:14];
  assign mem_0_1_W0_en = W0_en;
  assign mem_0_1_W0_mask = W0_mask[1];
  assign mem_0_1_R0_addr = R0_addr;
  assign mem_0_1_R0_clk = R0_clk;
  assign mem_0_1_R0_en = R0_en;
  assign mem_0_2_W0_addr = W0_addr;
  assign mem_0_2_W0_clk = W0_clk;
  assign mem_0_2_W0_data = W0_data[41:28];
  assign mem_0_2_W0_en = W0_en;
  assign mem_0_2_W0_mask = W0_mask[2];
  assign mem_0_2_R0_addr = R0_addr;
  assign mem_0_2_R0_clk = R0_clk;
  assign mem_0_2_R0_en = R0_en;
  assign mem_0_3_W0_addr = W0_addr;
  assign mem_0_3_W0_clk = W0_clk;
  assign mem_0_3_W0_data = W0_data[55:42];
  assign mem_0_3_W0_en = W0_en;
  assign mem_0_3_W0_mask = W0_mask[3];
  assign mem_0_3_R0_addr = R0_addr;
  assign mem_0_3_R0_clk = R0_clk;
  assign mem_0_3_R0_en = R0_en;
endmodule
module ebtb_ext(
  input  [6:0]  W0_addr,
  input         W0_clk,
  input  [39:0] W0_data,
  input         W0_en,
  input  [6:0]  R0_addr,
  input         R0_clk,
  output [39:0] R0_data,
  input         R0_en
);
  wire [6:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire [39:0] mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire [6:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire [39:0] mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [39:0] R0_data_0_0 = mem_0_0_R0_data;
  wire [39:0] R0_data_0 = R0_data_0_0;
  split_ebtb_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  assign R0_data = mem_0_0_R0_data;
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data;
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
endmodule
module data_ext(
  input  [10:0] W0_addr,
  input         W0_clk,
  input  [7:0]  W0_data,
  input         W0_en,
  input  [3:0]  W0_mask,
  input  [10:0] R0_addr,
  input         R0_clk,
  output [7:0]  R0_data,
  input         R0_en
);
  wire [10:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire [1:0] mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire  mem_0_0_W0_mask;
  wire [10:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire [1:0] mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [10:0] mem_0_1_W0_addr;
  wire  mem_0_1_W0_clk;
  wire [1:0] mem_0_1_W0_data;
  wire  mem_0_1_W0_en;
  wire  mem_0_1_W0_mask;
  wire [10:0] mem_0_1_R0_addr;
  wire  mem_0_1_R0_clk;
  wire [1:0] mem_0_1_R0_data;
  wire  mem_0_1_R0_en;
  wire [10:0] mem_0_2_W0_addr;
  wire  mem_0_2_W0_clk;
  wire [1:0] mem_0_2_W0_data;
  wire  mem_0_2_W0_en;
  wire  mem_0_2_W0_mask;
  wire [10:0] mem_0_2_R0_addr;
  wire  mem_0_2_R0_clk;
  wire [1:0] mem_0_2_R0_data;
  wire  mem_0_2_R0_en;
  wire [10:0] mem_0_3_W0_addr;
  wire  mem_0_3_W0_clk;
  wire [1:0] mem_0_3_W0_data;
  wire  mem_0_3_W0_en;
  wire  mem_0_3_W0_mask;
  wire [10:0] mem_0_3_R0_addr;
  wire  mem_0_3_R0_clk;
  wire [1:0] mem_0_3_R0_data;
  wire  mem_0_3_R0_en;
  wire [1:0] R0_data_0_0 = mem_0_0_R0_data;
  wire [1:0] R0_data_0_1 = mem_0_1_R0_data;
  wire [1:0] R0_data_0_2 = mem_0_2_R0_data;
  wire [1:0] R0_data_0_3 = mem_0_3_R0_data;
  wire [3:0] _GEN_0 = {R0_data_0_1,R0_data_0_0};
  wire [5:0] _GEN_1 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [7:0] R0_data_0 = {R0_data_0_3,R0_data_0_2,R0_data_0_1,R0_data_0_0};
  wire [3:0] _GEN_2 = {R0_data_0_1,R0_data_0_0};
  wire [5:0] _GEN_3 = {R0_data_0_2,R0_data_0_1,R0_data_0_0};
  split_data_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .W0_mask(mem_0_0_W0_mask),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  split_data_ext mem_0_1 (
    .W0_addr(mem_0_1_W0_addr),
    .W0_clk(mem_0_1_W0_clk),
    .W0_data(mem_0_1_W0_data),
    .W0_en(mem_0_1_W0_en),
    .W0_mask(mem_0_1_W0_mask),
    .R0_addr(mem_0_1_R0_addr),
    .R0_clk(mem_0_1_R0_clk),
    .R0_data(mem_0_1_R0_data),
    .R0_en(mem_0_1_R0_en)
  );
  split_data_ext mem_0_2 (
    .W0_addr(mem_0_2_W0_addr),
    .W0_clk(mem_0_2_W0_clk),
    .W0_data(mem_0_2_W0_data),
    .W0_en(mem_0_2_W0_en),
    .W0_mask(mem_0_2_W0_mask),
    .R0_addr(mem_0_2_R0_addr),
    .R0_clk(mem_0_2_R0_clk),
    .R0_data(mem_0_2_R0_data),
    .R0_en(mem_0_2_R0_en)
  );
  split_data_ext mem_0_3 (
    .W0_addr(mem_0_3_W0_addr),
    .W0_clk(mem_0_3_W0_clk),
    .W0_data(mem_0_3_W0_data),
    .W0_en(mem_0_3_W0_en),
    .W0_mask(mem_0_3_W0_mask),
    .R0_addr(mem_0_3_R0_addr),
    .R0_clk(mem_0_3_R0_clk),
    .R0_data(mem_0_3_R0_data),
    .R0_en(mem_0_3_R0_en)
  );
  assign R0_data = {R0_data_0_3,_GEN_1};
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data[1:0];
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_W0_mask = W0_mask[0];
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
  assign mem_0_1_W0_addr = W0_addr;
  assign mem_0_1_W0_clk = W0_clk;
  assign mem_0_1_W0_data = W0_data[3:2];
  assign mem_0_1_W0_en = W0_en;
  assign mem_0_1_W0_mask = W0_mask[1];
  assign mem_0_1_R0_addr = R0_addr;
  assign mem_0_1_R0_clk = R0_clk;
  assign mem_0_1_R0_en = R0_en;
  assign mem_0_2_W0_addr = W0_addr;
  assign mem_0_2_W0_clk = W0_clk;
  assign mem_0_2_W0_data = W0_data[5:4];
  assign mem_0_2_W0_en = W0_en;
  assign mem_0_2_W0_mask = W0_mask[2];
  assign mem_0_2_R0_addr = R0_addr;
  assign mem_0_2_R0_clk = R0_clk;
  assign mem_0_2_R0_en = R0_en;
  assign mem_0_3_W0_addr = W0_addr;
  assign mem_0_3_W0_clk = W0_clk;
  assign mem_0_3_W0_data = W0_data[7:6];
  assign mem_0_3_W0_en = W0_en;
  assign mem_0_3_W0_mask = W0_mask[3];
  assign mem_0_3_R0_addr = R0_addr;
  assign mem_0_3_R0_clk = R0_clk;
  assign mem_0_3_R0_en = R0_en;
endmodule
module meta_ext(
  input  [4:0]   W0_addr,
  input          W0_clk,
  input  [119:0] W0_data,
  input          W0_en,
  input  [4:0]   R0_addr,
  input          R0_clk,
  output [119:0] R0_data,
  input          R0_en
);
  wire [4:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire [119:0] mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire [4:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire [119:0] mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [119:0] R0_data_0_0 = mem_0_0_R0_data;
  wire [119:0] R0_data_0 = R0_data_0_0;
  split_meta_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  assign R0_data = mem_0_0_R0_data;
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data;
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
endmodule
module ghist_0_ext(
  input  [4:0]  W0_addr,
  input         W0_clk,
  input  [71:0] W0_data,
  input         W0_en,
  input  [4:0]  R0_addr,
  input         R0_clk,
  output [71:0] R0_data,
  input         R0_en
);
  wire [4:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire [71:0] mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire [4:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire [71:0] mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [71:0] R0_data_0_0 = mem_0_0_R0_data;
  wire [71:0] R0_data_0 = R0_data_0_0;
  split_ghist_0_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  assign R0_data = mem_0_0_R0_data;
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data;
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
endmodule
module rob_debug_inst_mem_ext(
  input  [4:0]  W0_addr,
  input         W0_clk,
  input  [63:0] W0_data,
  input         W0_en,
  input  [1:0]  W0_mask,
  input  [4:0]  R0_addr,
  input         R0_clk,
  output [63:0] R0_data,
  input         R0_en
);
  wire [4:0] mem_0_0_W0_addr;
  wire  mem_0_0_W0_clk;
  wire [31:0] mem_0_0_W0_data;
  wire  mem_0_0_W0_en;
  wire  mem_0_0_W0_mask;
  wire [4:0] mem_0_0_R0_addr;
  wire  mem_0_0_R0_clk;
  wire [31:0] mem_0_0_R0_data;
  wire  mem_0_0_R0_en;
  wire [4:0] mem_0_1_W0_addr;
  wire  mem_0_1_W0_clk;
  wire [31:0] mem_0_1_W0_data;
  wire  mem_0_1_W0_en;
  wire  mem_0_1_W0_mask;
  wire [4:0] mem_0_1_R0_addr;
  wire  mem_0_1_R0_clk;
  wire [31:0] mem_0_1_R0_data;
  wire  mem_0_1_R0_en;
  wire [31:0] R0_data_0_0 = mem_0_0_R0_data;
  wire [31:0] R0_data_0_1 = mem_0_1_R0_data;
  wire [63:0] R0_data_0 = {R0_data_0_1,R0_data_0_0};
  split_rob_debug_inst_mem_ext mem_0_0 (
    .W0_addr(mem_0_0_W0_addr),
    .W0_clk(mem_0_0_W0_clk),
    .W0_data(mem_0_0_W0_data),
    .W0_en(mem_0_0_W0_en),
    .W0_mask(mem_0_0_W0_mask),
    .R0_addr(mem_0_0_R0_addr),
    .R0_clk(mem_0_0_R0_clk),
    .R0_data(mem_0_0_R0_data),
    .R0_en(mem_0_0_R0_en)
  );
  split_rob_debug_inst_mem_ext mem_0_1 (
    .W0_addr(mem_0_1_W0_addr),
    .W0_clk(mem_0_1_W0_clk),
    .W0_data(mem_0_1_W0_data),
    .W0_en(mem_0_1_W0_en),
    .W0_mask(mem_0_1_W0_mask),
    .R0_addr(mem_0_1_R0_addr),
    .R0_clk(mem_0_1_R0_clk),
    .R0_data(mem_0_1_R0_data),
    .R0_en(mem_0_1_R0_en)
  );
  assign R0_data = {R0_data_0_1,R0_data_0_0};
  assign mem_0_0_W0_addr = W0_addr;
  assign mem_0_0_W0_clk = W0_clk;
  assign mem_0_0_W0_data = W0_data[31:0];
  assign mem_0_0_W0_en = W0_en;
  assign mem_0_0_W0_mask = W0_mask[0];
  assign mem_0_0_R0_addr = R0_addr;
  assign mem_0_0_R0_clk = R0_clk;
  assign mem_0_0_R0_en = R0_en;
  assign mem_0_1_W0_addr = W0_addr;
  assign mem_0_1_W0_clk = W0_clk;
  assign mem_0_1_W0_data = W0_data[63:32];
  assign mem_0_1_W0_en = W0_en;
  assign mem_0_1_W0_mask = W0_mask[1];
  assign mem_0_1_R0_addr = R0_addr;
  assign mem_0_1_R0_clk = R0_clk;
  assign mem_0_1_R0_en = R0_en;
endmodule
module l2_tlb_ram_ext(
  input  [8:0]  RW0_addr,
  input         RW0_clk,
  input  [44:0] RW0_wdata,
  output [44:0] RW0_rdata,
  input         RW0_en,
  input         RW0_wmode
);
  wire [8:0] mem_0_0_RW0_addr;
  wire  mem_0_0_RW0_clk;
  wire [44:0] mem_0_0_RW0_wdata;
  wire [44:0] mem_0_0_RW0_rdata;
  wire  mem_0_0_RW0_en;
  wire  mem_0_0_RW0_wmode;
  wire [44:0] RW0_rdata_0_0 = mem_0_0_RW0_rdata;
  wire [44:0] RW0_rdata_0 = RW0_rdata_0_0;
  split_l2_tlb_ram_ext mem_0_0 (
    .RW0_addr(mem_0_0_RW0_addr),
    .RW0_clk(mem_0_0_RW0_clk),
    .RW0_wdata(mem_0_0_RW0_wdata),
    .RW0_rdata(mem_0_0_RW0_rdata),
    .RW0_en(mem_0_0_RW0_en),
    .RW0_wmode(mem_0_0_RW0_wmode)
  );
  assign RW0_rdata = mem_0_0_RW0_rdata;
  assign mem_0_0_RW0_addr = RW0_addr;
  assign mem_0_0_RW0_clk = RW0_clk;
  assign mem_0_0_RW0_wdata = RW0_wdata;
  assign mem_0_0_RW0_en = RW0_en;
  assign mem_0_0_RW0_wmode = RW0_wmode;
endmodule
module split_cc_dir_ext(
  input  [9:0]  RW0_addr,
  input         RW0_clk,
  input  [18:0] RW0_wdata,
  output [18:0] RW0_rdata,
  input         RW0_en,
  input         RW0_wmode,
  input         RW0_wmask
);
`ifdef RANDOMIZE_MEM_INIT
  reg [31:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [18:0] ram [0:1023];
  wire [18:0] ram_RW_0_r_data;
  wire [9:0] ram_RW_0_r_addr;
  wire [18:0] ram_RW_0_w_data;
  wire [9:0] ram_RW_0_w_addr;
  wire  ram_RW_0_w_mask;
  wire  ram_RW_0_w_en;
  reg  ram_RW_0_r_en_pipe_0;
  reg [9:0] ram_RW_0_r_addr_pipe_0;
  wire  _GEN_0 = ~RW0_wmode;
  wire  _GEN_1 = ~RW0_wmode;
  assign ram_RW_0_r_addr = ram_RW_0_r_addr_pipe_0;
  assign ram_RW_0_r_data = ram[ram_RW_0_r_addr];
  assign ram_RW_0_w_data = RW0_wdata;
  assign ram_RW_0_w_addr = RW0_addr;
  assign ram_RW_0_w_mask = RW0_wmask;
  assign ram_RW_0_w_en = RW0_en & RW0_wmode;
  assign RW0_rdata = ram_RW_0_r_data;
  always @(posedge RW0_clk) begin
    if(ram_RW_0_w_en & ram_RW_0_w_mask) begin
      ram[ram_RW_0_w_addr] <= ram_RW_0_w_data;
    end
    ram_RW_0_r_en_pipe_0 <= RW0_en & ~RW0_wmode;
    if (RW0_en & ~RW0_wmode) begin
      ram_RW_0_r_addr_pipe_0 <= RW0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {1{`RANDOM}};
  for (initvar = 0; initvar < 1024; initvar = initvar+1)
    ram[initvar] = _RAND_0[18:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_RW_0_r_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_RW_0_r_addr_pipe_0 = _RAND_2[9:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_cc_banks_0_ext(
  input  [13:0] RW0_addr,
  input         RW0_clk,
  input  [63:0] RW0_wdata,
  output [63:0] RW0_rdata,
  input         RW0_en,
  input         RW0_wmode
);
`ifdef RANDOMIZE_MEM_INIT
  reg [63:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [63:0] ram [0:16383];
  wire [63:0] ram_RW_0_r_data;
  wire [13:0] ram_RW_0_r_addr;
  wire [63:0] ram_RW_0_w_data;
  wire [13:0] ram_RW_0_w_addr;
  wire  ram_RW_0_w_mask;
  wire  ram_RW_0_w_en;
  reg  ram_RW_0_r_en_pipe_0;
  reg [13:0] ram_RW_0_r_addr_pipe_0;
  wire  _GEN_0 = ~RW0_wmode;
  wire  _GEN_1 = ~RW0_wmode;
  assign ram_RW_0_r_addr = ram_RW_0_r_addr_pipe_0;
  assign ram_RW_0_r_data = ram[ram_RW_0_r_addr];
  assign ram_RW_0_w_data = RW0_wdata;
  assign ram_RW_0_w_addr = RW0_addr;
  assign ram_RW_0_w_mask = 1'h1;
  assign ram_RW_0_w_en = RW0_en & RW0_wmode;
  assign RW0_rdata = ram_RW_0_r_data;
  always @(posedge RW0_clk) begin
    if(ram_RW_0_w_en & ram_RW_0_w_mask) begin
      ram[ram_RW_0_w_addr] <= ram_RW_0_w_data;
    end
    ram_RW_0_r_en_pipe_0 <= RW0_en & ~RW0_wmode;
    if (RW0_en & ~RW0_wmode) begin
      ram_RW_0_r_addr_pipe_0 <= RW0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {2{`RANDOM}};
  for (initvar = 0; initvar < 16384; initvar = initvar+1)
    ram[initvar] = _RAND_0[63:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_RW_0_r_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_RW_0_r_addr_pipe_0 = _RAND_2[13:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_tag_array_ext(
  input  [5:0]  RW0_addr,
  input         RW0_clk,
  input  [21:0] RW0_wdata,
  output [21:0] RW0_rdata,
  input         RW0_en,
  input         RW0_wmode,
  input         RW0_wmask
);
`ifdef RANDOMIZE_MEM_INIT
  reg [31:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [21:0] ram [0:63];
  wire [21:0] ram_RW_0_r_data;
  wire [5:0] ram_RW_0_r_addr;
  wire [21:0] ram_RW_0_w_data;
  wire [5:0] ram_RW_0_w_addr;
  wire  ram_RW_0_w_mask;
  wire  ram_RW_0_w_en;
  reg  ram_RW_0_r_en_pipe_0;
  reg [5:0] ram_RW_0_r_addr_pipe_0;
  wire  _GEN_0 = ~RW0_wmode;
  wire  _GEN_1 = ~RW0_wmode;
  assign ram_RW_0_r_addr = ram_RW_0_r_addr_pipe_0;
  assign ram_RW_0_r_data = ram[ram_RW_0_r_addr];
  assign ram_RW_0_w_data = RW0_wdata;
  assign ram_RW_0_w_addr = RW0_addr;
  assign ram_RW_0_w_mask = RW0_wmask;
  assign ram_RW_0_w_en = RW0_en & RW0_wmode;
  assign RW0_rdata = ram_RW_0_r_data;
  always @(posedge RW0_clk) begin
    if(ram_RW_0_w_en & ram_RW_0_w_mask) begin
      ram[ram_RW_0_w_addr] <= ram_RW_0_w_data;
    end
    ram_RW_0_r_en_pipe_0 <= RW0_en & ~RW0_wmode;
    if (RW0_en & ~RW0_wmode) begin
      ram_RW_0_r_addr_pipe_0 <= RW0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {1{`RANDOM}};
  for (initvar = 0; initvar < 64; initvar = initvar+1)
    ram[initvar] = _RAND_0[21:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_RW_0_r_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_RW_0_r_addr_pipe_0 = _RAND_2[5:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_array_0_0_ext(
  input  [8:0]  W0_addr,
  input         W0_clk,
  input  [63:0] W0_data,
  input         W0_en,
  input         W0_mask,
  input  [8:0]  R0_addr,
  input         R0_clk,
  output [63:0] R0_data,
  input         R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [63:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [63:0] ram [0:511];
  wire [63:0] ram_R_0_data;
  wire [8:0] ram_R_0_addr;
  wire [63:0] ram_W_0_data;
  wire [8:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [8:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = W0_mask;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {2{`RANDOM}};
  for (initvar = 0; initvar < 512; initvar = initvar+1)
    ram[initvar] = _RAND_0[63:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[8:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_tag_array_0_ext(
  input  [5:0]  RW0_addr,
  input         RW0_clk,
  input  [19:0] RW0_wdata,
  output [19:0] RW0_rdata,
  input         RW0_en,
  input         RW0_wmode,
  input         RW0_wmask
);
`ifdef RANDOMIZE_MEM_INIT
  reg [31:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [19:0] ram [0:63];
  wire [19:0] ram_RW_0_r_data;
  wire [5:0] ram_RW_0_r_addr;
  wire [19:0] ram_RW_0_w_data;
  wire [5:0] ram_RW_0_w_addr;
  wire  ram_RW_0_w_mask;
  wire  ram_RW_0_w_en;
  reg  ram_RW_0_r_en_pipe_0;
  reg [5:0] ram_RW_0_r_addr_pipe_0;
  wire  _GEN_0 = ~RW0_wmode;
  wire  _GEN_1 = ~RW0_wmode;
  assign ram_RW_0_r_addr = ram_RW_0_r_addr_pipe_0;
  assign ram_RW_0_r_data = ram[ram_RW_0_r_addr];
  assign ram_RW_0_w_data = RW0_wdata;
  assign ram_RW_0_w_addr = RW0_addr;
  assign ram_RW_0_w_mask = RW0_wmask;
  assign ram_RW_0_w_en = RW0_en & RW0_wmode;
  assign RW0_rdata = ram_RW_0_r_data;
  always @(posedge RW0_clk) begin
    if(ram_RW_0_w_en & ram_RW_0_w_mask) begin
      ram[ram_RW_0_w_addr] <= ram_RW_0_w_data;
    end
    ram_RW_0_r_en_pipe_0 <= RW0_en & ~RW0_wmode;
    if (RW0_en & ~RW0_wmode) begin
      ram_RW_0_r_addr_pipe_0 <= RW0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {1{`RANDOM}};
  for (initvar = 0; initvar < 64; initvar = initvar+1)
    ram[initvar] = _RAND_0[19:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_RW_0_r_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_RW_0_r_addr_pipe_0 = _RAND_2[5:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_dataArrayWay_0_ext(
  input  [8:0]  RW0_addr,
  input         RW0_clk,
  input  [63:0] RW0_wdata,
  output [63:0] RW0_rdata,
  input         RW0_en,
  input         RW0_wmode
);
`ifdef RANDOMIZE_MEM_INIT
  reg [63:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [63:0] ram [0:511];
  wire [63:0] ram_RW_0_r_data;
  wire [8:0] ram_RW_0_r_addr;
  wire [63:0] ram_RW_0_w_data;
  wire [8:0] ram_RW_0_w_addr;
  wire  ram_RW_0_w_mask;
  wire  ram_RW_0_w_en;
  reg  ram_RW_0_r_en_pipe_0;
  reg [8:0] ram_RW_0_r_addr_pipe_0;
  wire  _GEN_0 = ~RW0_wmode;
  wire  _GEN_1 = ~RW0_wmode;
  assign ram_RW_0_r_addr = ram_RW_0_r_addr_pipe_0;
  assign ram_RW_0_r_data = ram[ram_RW_0_r_addr];
  assign ram_RW_0_w_data = RW0_wdata;
  assign ram_RW_0_w_addr = RW0_addr;
  assign ram_RW_0_w_mask = 1'h1;
  assign ram_RW_0_w_en = RW0_en & RW0_wmode;
  assign RW0_rdata = ram_RW_0_r_data;
  always @(posedge RW0_clk) begin
    if(ram_RW_0_w_en & ram_RW_0_w_mask) begin
      ram[ram_RW_0_w_addr] <= ram_RW_0_w_data;
    end
    ram_RW_0_r_en_pipe_0 <= RW0_en & ~RW0_wmode;
    if (RW0_en & ~RW0_wmode) begin
      ram_RW_0_r_addr_pipe_0 <= RW0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {2{`RANDOM}};
  for (initvar = 0; initvar < 512; initvar = initvar+1)
    ram[initvar] = _RAND_0[63:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_RW_0_r_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_RW_0_r_addr_pipe_0 = _RAND_2[8:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_hi_us_ext(
  input  [6:0] W0_addr,
  input        W0_clk,
  input        W0_data,
  input        W0_en,
  input        W0_mask,
  input  [6:0] R0_addr,
  input        R0_clk,
  output       R0_data,
  input        R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [31:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg  ram [0:127];
  wire  ram_R_0_data;
  wire [6:0] ram_R_0_addr;
  wire  ram_W_0_data;
  wire [6:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [6:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = W0_mask;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {1{`RANDOM}};
  for (initvar = 0; initvar < 128; initvar = initvar+1)
    ram[initvar] = _RAND_0[0:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[6:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_table_ext(
  input  [6:0]  W0_addr,
  input         W0_clk,
  input  [10:0] W0_data,
  input         W0_en,
  input         W0_mask,
  input  [6:0]  R0_addr,
  input         R0_clk,
  output [10:0] R0_data,
  input         R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [31:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [10:0] ram [0:127];
  wire [10:0] ram_R_0_data;
  wire [6:0] ram_R_0_addr;
  wire [10:0] ram_W_0_data;
  wire [6:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [6:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = W0_mask;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {1{`RANDOM}};
  for (initvar = 0; initvar < 128; initvar = initvar+1)
    ram[initvar] = _RAND_0[10:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[6:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_hi_us_0_ext(
  input  [7:0] W0_addr,
  input        W0_clk,
  input        W0_data,
  input        W0_en,
  input        W0_mask,
  input  [7:0] R0_addr,
  input        R0_clk,
  output       R0_data,
  input        R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [31:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg  ram [0:255];
  wire  ram_R_0_data;
  wire [7:0] ram_R_0_addr;
  wire  ram_W_0_data;
  wire [7:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [7:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = W0_mask;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {1{`RANDOM}};
  for (initvar = 0; initvar < 256; initvar = initvar+1)
    ram[initvar] = _RAND_0[0:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[7:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_table_0_ext(
  input  [7:0]  W0_addr,
  input         W0_clk,
  input  [11:0] W0_data,
  input         W0_en,
  input         W0_mask,
  input  [7:0]  R0_addr,
  input         R0_clk,
  output [11:0] R0_data,
  input         R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [31:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [11:0] ram [0:255];
  wire [11:0] ram_R_0_data;
  wire [7:0] ram_R_0_addr;
  wire [11:0] ram_W_0_data;
  wire [7:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [7:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = W0_mask;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {1{`RANDOM}};
  for (initvar = 0; initvar < 256; initvar = initvar+1)
    ram[initvar] = _RAND_0[11:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[7:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_table_1_ext(
  input  [6:0]  W0_addr,
  input         W0_clk,
  input  [12:0] W0_data,
  input         W0_en,
  input         W0_mask,
  input  [6:0]  R0_addr,
  input         R0_clk,
  output [12:0] R0_data,
  input         R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [31:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [12:0] ram [0:127];
  wire [12:0] ram_R_0_data;
  wire [6:0] ram_R_0_addr;
  wire [12:0] ram_W_0_data;
  wire [6:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [6:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = W0_mask;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {1{`RANDOM}};
  for (initvar = 0; initvar < 128; initvar = initvar+1)
    ram[initvar] = _RAND_0[12:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[6:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_meta_0_ext(
  input  [6:0]  W0_addr,
  input         W0_clk,
  input  [30:0] W0_data,
  input         W0_en,
  input         W0_mask,
  input  [6:0]  R0_addr,
  input         R0_clk,
  output [30:0] R0_data,
  input         R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [31:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [30:0] ram [0:127];
  wire [30:0] ram_R_0_data;
  wire [6:0] ram_R_0_addr;
  wire [30:0] ram_W_0_data;
  wire [6:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [6:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = W0_mask;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {1{`RANDOM}};
  for (initvar = 0; initvar < 128; initvar = initvar+1)
    ram[initvar] = _RAND_0[30:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[6:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_btb_0_ext(
  input  [6:0]  W0_addr,
  input         W0_clk,
  input  [13:0] W0_data,
  input         W0_en,
  input         W0_mask,
  input  [6:0]  R0_addr,
  input         R0_clk,
  output [13:0] R0_data,
  input         R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [31:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [13:0] ram [0:127];
  wire [13:0] ram_R_0_data;
  wire [6:0] ram_R_0_addr;
  wire [13:0] ram_W_0_data;
  wire [6:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [6:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = W0_mask;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {1{`RANDOM}};
  for (initvar = 0; initvar < 128; initvar = initvar+1)
    ram[initvar] = _RAND_0[13:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[6:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_ebtb_ext(
  input  [6:0]  W0_addr,
  input         W0_clk,
  input  [39:0] W0_data,
  input         W0_en,
  input  [6:0]  R0_addr,
  input         R0_clk,
  output [39:0] R0_data,
  input         R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [63:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [39:0] ram [0:127];
  wire [39:0] ram_R_0_data;
  wire [6:0] ram_R_0_addr;
  wire [39:0] ram_W_0_data;
  wire [6:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [6:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = 1'h1;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {2{`RANDOM}};
  for (initvar = 0; initvar < 128; initvar = initvar+1)
    ram[initvar] = _RAND_0[39:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[6:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_data_ext(
  input  [10:0] W0_addr,
  input         W0_clk,
  input  [1:0]  W0_data,
  input         W0_en,
  input         W0_mask,
  input  [10:0] R0_addr,
  input         R0_clk,
  output [1:0]  R0_data,
  input         R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [31:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [1:0] ram [0:2047];
  wire [1:0] ram_R_0_data;
  wire [10:0] ram_R_0_addr;
  wire [1:0] ram_W_0_data;
  wire [10:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [10:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = W0_mask;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {1{`RANDOM}};
  for (initvar = 0; initvar < 2048; initvar = initvar+1)
    ram[initvar] = _RAND_0[1:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[10:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_meta_ext(
  input  [4:0]   W0_addr,
  input          W0_clk,
  input  [119:0] W0_data,
  input          W0_en,
  input  [4:0]   R0_addr,
  input          R0_clk,
  output [119:0] R0_data,
  input          R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [127:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [119:0] ram [0:31];
  wire [119:0] ram_R_0_data;
  wire [4:0] ram_R_0_addr;
  wire [119:0] ram_W_0_data;
  wire [4:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [4:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = 1'h1;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {4{`RANDOM}};
  for (initvar = 0; initvar < 32; initvar = initvar+1)
    ram[initvar] = _RAND_0[119:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[4:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_ghist_0_ext(
  input  [4:0]  W0_addr,
  input         W0_clk,
  input  [71:0] W0_data,
  input         W0_en,
  input  [4:0]  R0_addr,
  input         R0_clk,
  output [71:0] R0_data,
  input         R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [95:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [71:0] ram [0:31];
  wire [71:0] ram_R_0_data;
  wire [4:0] ram_R_0_addr;
  wire [71:0] ram_W_0_data;
  wire [4:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [4:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = 1'h1;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {3{`RANDOM}};
  for (initvar = 0; initvar < 32; initvar = initvar+1)
    ram[initvar] = _RAND_0[71:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[4:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_rob_debug_inst_mem_ext(
  input  [4:0]  W0_addr,
  input         W0_clk,
  input  [31:0] W0_data,
  input         W0_en,
  input         W0_mask,
  input  [4:0]  R0_addr,
  input         R0_clk,
  output [31:0] R0_data,
  input         R0_en
);
`ifdef RANDOMIZE_MEM_INIT
  reg [31:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [31:0] ram [0:31];
  wire [31:0] ram_R_0_data;
  wire [4:0] ram_R_0_addr;
  wire [31:0] ram_W_0_data;
  wire [4:0] ram_W_0_addr;
  wire  ram_W_0_mask;
  wire  ram_W_0_en;
  reg  ram_R_0_en_pipe_0;
  reg [4:0] ram_R_0_addr_pipe_0;
  assign ram_R_0_addr = ram_R_0_addr_pipe_0;
  assign ram_R_0_data = ram[ram_R_0_addr];
  assign ram_W_0_data = W0_data;
  assign ram_W_0_addr = W0_addr;
  assign ram_W_0_mask = W0_mask;
  assign ram_W_0_en = W0_en;
  assign R0_data = ram_R_0_data;
  always @(posedge W0_clk) begin
    if(ram_W_0_en & ram_W_0_mask) begin
      ram[ram_W_0_addr] <= ram_W_0_data;
    end
  end
  always @(posedge R0_clk) begin
    ram_R_0_en_pipe_0 <= R0_en;
    if (R0_en) begin
      ram_R_0_addr_pipe_0 <= R0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {1{`RANDOM}};
  for (initvar = 0; initvar < 32; initvar = initvar+1)
    ram[initvar] = _RAND_0[31:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_R_0_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_R_0_addr_pipe_0 = _RAND_2[4:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
module split_l2_tlb_ram_ext(
  input  [8:0]  RW0_addr,
  input         RW0_clk,
  input  [44:0] RW0_wdata,
  output [44:0] RW0_rdata,
  input         RW0_en,
  input         RW0_wmode
);
`ifdef RANDOMIZE_MEM_INIT
  reg [63:0] _RAND_0;
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_1;
  reg [31:0] _RAND_2;
`endif // RANDOMIZE_REG_INIT
  reg [44:0] ram [0:511];
  wire [44:0] ram_RW_0_r_data;
  wire [8:0] ram_RW_0_r_addr;
  wire [44:0] ram_RW_0_w_data;
  wire [8:0] ram_RW_0_w_addr;
  wire  ram_RW_0_w_mask;
  wire  ram_RW_0_w_en;
  reg  ram_RW_0_r_en_pipe_0;
  reg [8:0] ram_RW_0_r_addr_pipe_0;
  wire  _GEN_0 = ~RW0_wmode;
  wire  _GEN_1 = ~RW0_wmode;
  assign ram_RW_0_r_addr = ram_RW_0_r_addr_pipe_0;
  assign ram_RW_0_r_data = ram[ram_RW_0_r_addr];
  assign ram_RW_0_w_data = RW0_wdata;
  assign ram_RW_0_w_addr = RW0_addr;
  assign ram_RW_0_w_mask = 1'h1;
  assign ram_RW_0_w_en = RW0_en & RW0_wmode;
  assign RW0_rdata = ram_RW_0_r_data;
  always @(posedge RW0_clk) begin
    if(ram_RW_0_w_en & ram_RW_0_w_mask) begin
      ram[ram_RW_0_w_addr] <= ram_RW_0_w_data;
    end
    ram_RW_0_r_en_pipe_0 <= RW0_en & ~RW0_wmode;
    if (RW0_en & ~RW0_wmode) begin
      ram_RW_0_r_addr_pipe_0 <= RW0_addr;
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_MEM_INIT
  _RAND_0 = {2{`RANDOM}};
  for (initvar = 0; initvar < 512; initvar = initvar+1)
    ram[initvar] = _RAND_0[44:0];
`endif // RANDOMIZE_MEM_INIT
`ifdef RANDOMIZE_REG_INIT
  _RAND_1 = {1{`RANDOM}};
  ram_RW_0_r_en_pipe_0 = _RAND_1[0:0];
  _RAND_2 = {1{`RANDOM}};
  ram_RW_0_r_addr_pipe_0 = _RAND_2[8:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
