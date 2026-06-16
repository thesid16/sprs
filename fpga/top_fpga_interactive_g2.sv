// =============================================================================
// top_fpga_interactive_g2.sv — RDMA-Push FPGA Wrapper (Nexys A7)
//
// Configuration: G=2, linear topology, 8-leaf binary tree, FADD-only
//   Compiler config: S2=HEFT(2a), S3=Identity(3a), S4=None(4a)
//   Makespan: 21 cycles
//
//   GPU 0: root aggregator — 6 GEN, 5 COMPUTE (33 instrs)
//   GPU 1: subtree + SEND — 2 GEN, 1 COMPUTE, 1 SEND (11 instrs)
//
// RDMA-Push: No OP_RECV. GPU 1 SENDs with target_addr embedded in packet.
// GPU 0's scoreboard auto-stalls COMPUTE until PIU writes arrive.
//
// Usage after bitstream load:
//   1. Set vio_leaf_value to the 64-bit FP64 leaf value
//   2. Set vio_leaf_idx to the leaf index (0-7)
//   3. Toggle vio_leaf_wr from 0→1→0 to latch the value
//   4. Repeat for all 8 leaves
//   5. Toggle vio_start from 0→1 OR flip SW[0] to trigger reduction
//   6. Read vio_result and vio_perf_cycles from output probes
//   7. Result displayed on 7-segment display in hex
// =============================================================================
`timescale 1ns / 1ps

module top_fpga_interactive_g2 (
    input  logic        sys_clk,
    input  logic        btn_rst,
    input  logic        sw_start,     // SW[0] — physical switch to trigger reduction
    output logic        led_done,
    output logic [7:0]  led,
    output logic [6:0]  seg,          // 7-segment cathodes (active low) CA-CG
    output logic        dp,           // 7-segment decimal point (active low)
    output logic [7:0]  an            // 7-segment anodes (active low)
);

    // ── Clock & Reset ──
    logic clk, rst;
    assign clk = sys_clk;
    logic [2:0] rst_sync;
    always_ff @(posedge clk) rst_sync <= {rst_sync[1:0], btn_rst};
    assign rst = rst_sync[2];

    // ── Parameters ──
    localparam int NN = 2;   // 2 GPUs
    localparam int NR = 2;   // 2 Routers
    localparam int PP = 3;   // 3 ports per router (linear: local + 2 ring but 1 disconnected)

    // Compiler-derived constants
    localparam int G0_SZ = 33;
    localparam int G1_SZ = 11;
    localparam int MAX_LEAVES_PER_GPU = 6;  // from compiler: GPU 0 has 6 leaves
    localparam int TOTAL_LEAVES = 8;

    // ── noc_system signals ──
    logic        program_start, all_done;
    logic [63:0] sys_result;
    logic [NN-1:0][7:0]  sys_status;
    logic [NN-1:0]       sys_error;
    logic [NN-1:0][15:0] error_pc;
    logic [NN-1:0][3:0]  error_state;

    logic [NN-1:0]        imem_wr_en;
    logic [NN-1:0][15:0]  imem_wr_addr, imem_size;
    logic [NN-1:0][63:0]  imem_wr_data;

    logic [NR-1:0]        rtr_rt_wr_en;
    logic [NR-1:0][15:0]  rtr_rt_wr_addr;
    logic [NR-1:0][$clog2(PP)-1:0] rtr_rt_wr_data;

    logic                 adj_wr_en;
    logic [11:0]          adj_rtr_id, adj_port_id, adj_target_rtr, adj_target_port;

    logic [NN-1:0]        gci_buf_wr_en;
    logic [NN-1:0][15:0]  gci_buf_wr_addr;
    logic [NN-1:0][63:0]  gci_buf_wr_data;

    logic [NN-1:0][31:0]  perf_total, perf_stall, perf_retired;

    // ── noc_system instance (FPGA-sized) ──
    noc_system #(
        .N_NODES(NN), .N_ROUTERS(NR), .PORTS_PER_RTR(PP),
        .NUM_VCS(2), .GCI_BUF_DEPTH(MAX_LEAVES_PER_GPU),
        .RTR_BUF_DEPTH(4), .NI_BUF_DEPTH(4), .LINK_LATENCY(0),
        .CN_NUM_LINKS(2), .CN_TX_BUF(4), .CN_RX_BUF(4),
        .CN_DMEM(32), .CN_IMEM(64),
        .CN_TIMEOUT(5000), .CN_WATCHDOG(10000), .GCI_LATENCY(4)
    ) u_sys (
        .clk(clk), .rst(rst),
        .program_start(program_start), .all_done(all_done), .result(sys_result),
        .status(sys_status), .error(sys_error),
        .error_pc(error_pc), .error_state(error_state),
        .imem_wr_en(imem_wr_en), .imem_wr_addr(imem_wr_addr),
        .imem_wr_data(imem_wr_data), .imem_size(imem_size),
        .rtr_rt_wr_en(rtr_rt_wr_en), .rtr_rt_wr_addr(rtr_rt_wr_addr),
        .rtr_rt_wr_data(rtr_rt_wr_data),
        .adj_wr_en(adj_wr_en), .adj_rtr_id(adj_rtr_id),
        .adj_port_id(adj_port_id), .adj_target_rtr(adj_target_rtr),
        .adj_target_port(adj_target_port),
        .gci_buf_wr_en(gci_buf_wr_en), .gci_buf_wr_addr(gci_buf_wr_addr),
        .gci_buf_wr_data(gci_buf_wr_data),
        .perf_total(perf_total), .perf_stall(perf_stall), .perf_retired(perf_retired)
    );

    // ── Instruction ROMs (compiler-generated, RDMA-Push, FADD-only) ──
    // Source: find_optimal_fpga_schedule.py → optimal_g2_linear_config.json
    // Winner: S2=HEFT(2a), S3=Identity(3a), S4=None(4a), makespan=21
    logic [63:0] rom_gpu0 [0:G0_SZ-1];
    logic [63:0] rom_gpu1 [0:G1_SZ-1];

    initial begin
        // GPU 0: 33 instructions — root aggregator
        rom_gpu0[ 0] = 64'h1000010000000000;  // GEN  → D[1]
        rom_gpu0[ 1] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 2] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 3] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 4] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 5] = 64'h1000020000000000;  // GEN  → D[2]
        rom_gpu0[ 6] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 7] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 8] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 9] = 64'h2E00010002000100;  // COMP D[1]=D[2]+D[1]  (FADD)
        rom_gpu0[10] = 64'h1000020000000000;  // GEN  → D[2]
        rom_gpu0[11] = 64'h0000000000000000;  // NOP
        rom_gpu0[12] = 64'h0000000000000000;  // NOP
        rom_gpu0[13] = 64'h0000000000000000;  // NOP
        rom_gpu0[14] = 64'h0000000000000000;  // NOP
        rom_gpu0[15] = 64'h1000030000000000;  // GEN  → D[3]
        rom_gpu0[16] = 64'h0000000000000000;  // NOP
        rom_gpu0[17] = 64'h0000000000000000;  // NOP
        rom_gpu0[18] = 64'h0000000000000000;  // NOP
        rom_gpu0[19] = 64'h2E00020003000200;  // COMP D[2]=D[3]+D[2]  (FADD)
        rom_gpu0[20] = 64'h2E00010002000100;  // COMP D[1]=D[2]+D[1]  (FADD)
        rom_gpu0[21] = 64'h1000020000000000;  // GEN  → D[2]
        rom_gpu0[22] = 64'h0000000000000000;  // NOP
        rom_gpu0[23] = 64'h0000000000000000;  // NOP
        rom_gpu0[24] = 64'h0000000000000000;  // NOP
        rom_gpu0[25] = 64'h0000000000000000;  // NOP
        rom_gpu0[26] = 64'h1000030000000000;  // GEN  → D[3]
        rom_gpu0[27] = 64'h0000000000000000;  // NOP
        rom_gpu0[28] = 64'h0000000000000000;  // NOP
        rom_gpu0[29] = 64'h0000000000000000;  // NOP
        rom_gpu0[30] = 64'h2E00020003000200;  // COMP D[2]=D[3]+D[2]  (FADD)
        rom_gpu0[31] = 64'h2E00020002000400;  // COMP D[2]=D[2]+D[4]  (FADD, D[4] from RDMA)
        rom_gpu0[32] = 64'h2E00010002000100;  // COMP D[1]=D[2]+D[1]  (FADD, ROOT)

        // GPU 1: 11 instructions — subtree + SEND
        rom_gpu1[ 0] = 64'h1000010000000000;  // GEN  → D[1]
        rom_gpu1[ 1] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 2] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 3] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 4] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 5] = 64'h1000020000000000;  // GEN  → D[2]
        rom_gpu1[ 6] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 7] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 8] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 9] = 64'h2E00010002000100;  // COMP D[1]=D[2]+D[1]  (FADD)
        rom_gpu1[10] = 64'h3000040001000000;  // SEND dest=D[4]@GPU0, src=D[1]  (RDMA-Push)
    end

    // =========================================================================
    // VIO Signals
    // =========================================================================
    logic [63:0] vio_leaf_value;   // probe_out0: 64-bit leaf value to write
    logic [3:0]  vio_leaf_idx;     // probe_out1: which leaf (0-7)
    logic        vio_leaf_wr;      // probe_out2: rising edge = latch value
    logic        vio_start_vio;    // probe_out3: rising edge = start reduction

    // VIO INPUT probes (FPGA → user)
    logic [63:0] vio_result;
    logic        vio_done;
    logic [1:0]  vio_error;
    logic [31:0] vio_perf_cycles;
    logic [31:0] vio_perf_stalls;
    logic [7:0]  vio_state;

    assign vio_result      = sys_result;
    assign vio_done        = all_done;
    assign vio_error       = sys_error;
    assign vio_perf_cycles = perf_total[0];
    assign vio_perf_stalls = perf_stall[0];

    // =========================================================================
    // VIO IP Instantiation
    // =========================================================================
    `ifndef SIMULATION
    u_vio_0 u_vio_inst (
        .clk        (clk),
        .probe_in0  (vio_result),       // [63:0]
        .probe_in1  (vio_done),         // [0:0]
        .probe_in2  (vio_error),        // [1:0]
        .probe_in3  (vio_perf_cycles),  // [31:0]
        .probe_in4  (vio_perf_stalls),  // [31:0]
        .probe_in5  (vio_state),        // [7:0]
        .probe_out0 (vio_leaf_value),   // [63:0]
        .probe_out1 (vio_leaf_idx),     // [3:0]
        .probe_out2 (vio_leaf_wr),      // [0:0]
        .probe_out3 (vio_start_vio)     // [0:0]
    );
    `else
    assign vio_start_vio = 1'b0;
    `endif

    // =========================================================================
    // ILA IP Instantiation
    // =========================================================================
    logic [63:0] ila_gpu0_result, ila_gpu1_result;
    logic [7:0]  ila_gpu0_status, ila_gpu1_status;

    assign ila_gpu0_result = u_sys.cn_result[0];
    assign ila_gpu1_result = u_sys.cn_result[1];
    assign ila_gpu0_status = sys_status[0];
    assign ila_gpu1_status = sys_status[1];

    `ifndef SIMULATION
    u_ila_0 u_ila_inst (
        .clk    (clk),
        .probe0 (ila_gpu0_result),  // [63:0]
        .probe1 (ila_gpu1_result),  // [63:0]
        .probe2 (ila_gpu0_status),  // [7:0]
        .probe3 (ila_gpu1_status)   // [7:0]
    );
    `endif

    // =========================================================================
    // Switch Debounce + Start Trigger
    // =========================================================================
    logic [2:0]  sw_sync;
    logic        sw_debounced;
    logic        vio_start;

    always_ff @(posedge clk) sw_sync <= {sw_sync[1:0], sw_start};
    assign sw_debounced = sw_sync[2];
    assign vio_start = vio_start_vio | sw_debounced;

    // =========================================================================
    // 7-Segment Display Driver
    // =========================================================================
    logic [31:0] display_value;
    logic [16:0] refresh_counter;
    logic [2:0]  digit_sel;
    logic [3:0]  hex_digit;
    logic [6:0]  seg_pattern;

    always_ff @(posedge clk) begin
        if (rst) display_value <= 32'd0;
        else if (all_done) display_value <= sys_result[31:0];
    end

    always_ff @(posedge clk) begin
        if (rst) refresh_counter <= 17'd0;
        else     refresh_counter <= refresh_counter + 17'd1;
    end

    assign digit_sel = refresh_counter[16:14];

    always_comb begin
        case (digit_sel)
            3'd0: hex_digit = display_value[3:0];
            3'd1: hex_digit = display_value[7:4];
            3'd2: hex_digit = display_value[11:8];
            3'd3: hex_digit = display_value[15:12];
            3'd4: hex_digit = display_value[19:16];
            3'd5: hex_digit = display_value[23:20];
            3'd6: hex_digit = display_value[27:24];
            3'd7: hex_digit = display_value[31:28];
        endcase
    end

    always_comb begin
        case (hex_digit)
            4'h0: seg_pattern = 7'b0111111;  4'h1: seg_pattern = 7'b0000110;
            4'h2: seg_pattern = 7'b1011011;  4'h3: seg_pattern = 7'b1001111;
            4'h4: seg_pattern = 7'b1100110;  4'h5: seg_pattern = 7'b1101101;
            4'h6: seg_pattern = 7'b1111101;  4'h7: seg_pattern = 7'b0000111;
            4'h8: seg_pattern = 7'b1111111;  4'h9: seg_pattern = 7'b1101111;
            4'hA: seg_pattern = 7'b1110111;  4'hB: seg_pattern = 7'b1111100;
            4'hC: seg_pattern = 7'b0111001;  4'hD: seg_pattern = 7'b1011110;
            4'hE: seg_pattern = 7'b1111001;  4'hF: seg_pattern = 7'b1110001;
        endcase
    end

    assign seg = ~seg_pattern;
    assign dp  = 1'b1;

    always_comb begin
        an = 8'hFF;
        if (all_done) an[digit_sel] = 1'b0;
    end

    // =========================================================================
    // Config FSM + Leaf Loading + Start Control
    //
    // Compiler leaf-to-GPU assignment (from optimal_g2_linear_config.json):
    //   GPU 0 leaves: tree nodes 7,8,11,12,13,14 (6 leaves)
    //   GPU 1 leaves: tree nodes 9,10 (2 leaves)
    //   Global leaf idx 0-5 → GPU 0, idx 6-7 → GPU 1
    // =========================================================================
    typedef enum logic [3:0] {
        S_ADJ0, S_ADJ1,
        S_RT0, S_RT1, S_RT2, S_RT3,
        S_INSTR_GPU0, S_INSTR_GPU1,
        S_SIZE,
        S_WAIT_LEAVES,
        S_START, S_RUN, S_DONE
    } state_t;

    state_t     state;
    logic [5:0] counter;
    logic       vio_leaf_wr_prev;
    logic       vio_start_prev;

    assign vio_state = {4'd0, state};

    always_ff @(posedge clk) begin
        if (rst) begin
            state          <= S_ADJ0;
            counter        <= '0;
            program_start  <= 1'b0;
            imem_wr_en     <= '0;
            rtr_rt_wr_en   <= '0;
            adj_wr_en      <= 1'b0;
            imem_size      <= '0;
            gci_buf_wr_en  <= '0;
            led_done       <= 1'b0;
            led            <= '0;
            vio_leaf_wr_prev <= 1'b0;
            vio_start_prev   <= 1'b0;
        end else begin
            adj_wr_en      <= 1'b0;
            rtr_rt_wr_en   <= '0;
            imem_wr_en     <= '0;
            program_start  <= 1'b0;
            gci_buf_wr_en  <= '0;
            vio_leaf_wr_prev <= vio_leaf_wr;
            vio_start_prev   <= vio_start;

            case (state)
                // ── Adjacency: linear R0.p1 ↔ R1.p1 ──
                S_ADJ0: begin
                    adj_wr_en <= 1'b1;
                    adj_rtr_id <= 12'd0; adj_port_id <= 12'd1;
                    adj_target_rtr <= 12'd1; adj_target_port <= 12'd1;
                    state <= S_ADJ1;
                end
                S_ADJ1: begin
                    adj_wr_en <= 1'b1;
                    adj_rtr_id <= 12'd1; adj_port_id <= 12'd1;
                    adj_target_rtr <= 12'd0; adj_target_port <= 12'd1;
                    state <= S_RT0;
                end

                // ── Routing Tables ──
                // R0: dest 0→local(0), dest 1→port1
                // R1: dest 0→port1,    dest 1→local(0)
                S_RT0: begin rtr_rt_wr_en[0]<=1; rtr_rt_wr_addr[0]<=0; rtr_rt_wr_data[0]<=0; state<=S_RT1; end
                S_RT1: begin rtr_rt_wr_en[0]<=1; rtr_rt_wr_addr[0]<=1; rtr_rt_wr_data[0]<=1; state<=S_RT2; end
                S_RT2: begin rtr_rt_wr_en[1]<=1; rtr_rt_wr_addr[1]<=0; rtr_rt_wr_data[1]<=1; state<=S_RT3; end
                S_RT3: begin rtr_rt_wr_en[1]<=1; rtr_rt_wr_addr[1]<=1; rtr_rt_wr_data[1]<=0; state<=S_INSTR_GPU0; counter<='0; end

                // ── Instructions ──
                S_INSTR_GPU0: begin
                    imem_wr_en[0]   <= 1'b1;
                    imem_wr_addr[0] <= {10'd0, counter};
                    imem_wr_data[0] <= rom_gpu0[counter];
                    if (counter == G0_SZ - 1) begin state <= S_INSTR_GPU1; counter <= '0; end
                    else counter <= counter + 1;
                end
                S_INSTR_GPU1: begin
                    imem_wr_en[1]   <= 1'b1;
                    imem_wr_addr[1] <= {10'd0, counter};
                    imem_wr_data[1] <= rom_gpu1[counter];
                    if (counter == G1_SZ - 1) state <= S_SIZE;
                    else counter <= counter + 1;
                end

                S_SIZE: begin
                    imem_size[0] <= G0_SZ[15:0];
                    imem_size[1] <= G1_SZ[15:0];
                    state <= S_WAIT_LEAVES;
                    led <= 8'hAA;
                end

                // ── Wait for VIO leaf loading ──
                S_WAIT_LEAVES: begin
                    led <= 8'hAA;

                    if (vio_leaf_wr && !vio_leaf_wr_prev) begin
                        // Leaves 0-5 → GPU 0, 6-7 → GPU 1
                        if (vio_leaf_idx < 4'd6) begin
                            gci_buf_wr_en[0]   <= 1'b1;
                            gci_buf_wr_addr[0] <= {12'd0, vio_leaf_idx};
                            gci_buf_wr_data[0] <= vio_leaf_value;
                        end else begin
                            gci_buf_wr_en[1]   <= 1'b1;
                            gci_buf_wr_addr[1] <= {12'd0, vio_leaf_idx - 4'd6};
                            gci_buf_wr_data[1] <= vio_leaf_value;
                        end
                    end

                    if (vio_start && !vio_start_prev) begin
                        state <= S_START;
                    end
                end

                S_START: begin
                    program_start <= 1'b1;
                    led <= 8'h55;
                    state <= S_RUN;
                end

                S_RUN: begin
                    led <= 8'h55;
                    if (all_done) begin
                        led_done <= 1'b1;
                        led      <= sys_result[7:0];
                        state    <= S_DONE;
                    end
                end

                S_DONE: begin
                    led_done <= 1'b1;
                    led      <= sys_result[7:0];
                end

                default: ;
            endcase
        end
    end

endmodule
