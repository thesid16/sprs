// =============================================================================
// top_fpga_interactive_g4.sv — RDMA-Push FPGA Wrapper (Nexys A7)
//
// Configuration: G=4, ring topology, 8-leaf binary tree, FADD-only
//   Compiler config: S2=Spine(2p), S3=Identity(3a), S4=None(4a)
//   Makespan: 22 cycles
//
//   GPU 0: root aggregator — 1 GEN, 3 COMPUTE (14 instrs)
//   GPU 1: largest subtree  — 4 GEN, 3 COMPUTE, 1 SEND (22 instrs)
//   GPU 2: subtree + SEND   — 2 GEN, 1 COMPUTE, 1 SEND (11 instrs)
//   GPU 3: single leaf SEND — 1 GEN, 1 SEND (5 instrs)
//
// RDMA-Push: No OP_RECV. Senders embed target_addr in packets.
// Receivers auto-stall via scoreboard until PIU writes arrive.
// =============================================================================
`timescale 1ns / 1ps

module top_fpga_interactive_g4 (
    input  logic        sys_clk,
    input  logic        btn_rst,
    input  logic        sw_start,
    output logic        led_done,
    output logic [7:0]  led,
    output logic [6:0]  seg,
    output logic        dp,
    output logic [7:0]  an
);

    // ── Clock & Reset ──
    logic clk, rst;
    assign clk = sys_clk;
    logic [2:0] rst_sync;
    always_ff @(posedge clk) rst_sync <= {rst_sync[1:0], btn_rst};
    assign rst = rst_sync[2];

    // ── Parameters ──
    localparam int NN = 4;   // 4 GPUs
    localparam int NR = 4;   // 4 Routers
    localparam int PP = 3;   // 3 ports per router (local + 2 ring)

    // Compiler-derived constants
    localparam int G0_SZ = 14;
    localparam int G1_SZ = 22;
    localparam int G2_SZ = 11;
    localparam int G3_SZ = 5;
    localparam int MAX_GPU_SZ = 22;  // largest program
    localparam int MAX_LEAVES_PER_GPU = 4;  // from compiler: GPU 1 has 4 leaves
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
    // Source: find_optimal_fpga_schedule.py → optimal_g4_ring_config.json
    // Winner: S2=Spine(2p), S3=Identity(3a), S4=None(4a), makespan=22
    logic [63:0] rom_gpu0 [0:G0_SZ-1];
    logic [63:0] rom_gpu1 [0:G1_SZ-1];
    logic [63:0] rom_gpu2 [0:G2_SZ-1];
    logic [63:0] rom_gpu3 [0:G3_SZ-1];

    initial begin
        // GPU 0: 14 instructions — root aggregator (receives 3 sub-results via RDMA)
        rom_gpu0[ 0] = 64'h1000010000000000;  // GEN  → D[1]
        rom_gpu0[ 1] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 2] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 3] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 4] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 5] = 64'h2E00010001000200;  // COMP D[1]=D[1]+D[2]  (D[2] from RDMA, scoreboard stalls)
        rom_gpu0[ 6] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 7] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 8] = 64'h0000000000000000;  // NOP
        rom_gpu0[ 9] = 64'h0000000000000000;  // NOP
        rom_gpu0[10] = 64'h2E00010001000300;  // COMP D[1]=D[1]+D[3]  (D[3] from RDMA)
        rom_gpu0[11] = 64'h0000000000000000;  // NOP
        rom_gpu0[12] = 64'h0000000000000000;  // NOP
        rom_gpu0[13] = 64'h2E00010001000400;  // COMP D[1]=D[1]+D[4]  (D[4] from RDMA, ROOT)

        // GPU 1: 22 instructions — largest subtree (4 leaves, local reduction, SEND to GPU 0)
        rom_gpu1[ 0] = 64'h1000010000000000;  // GEN  → D[1]
        rom_gpu1[ 1] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 2] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 3] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 4] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 5] = 64'h1000020000000000;  // GEN  → D[2]
        rom_gpu1[ 6] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 7] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 8] = 64'h0000000000000000;  // NOP
        rom_gpu1[ 9] = 64'h2E00010002000100;  // COMP D[1]=D[2]+D[1]
        rom_gpu1[10] = 64'h1000020000000000;  // GEN  → D[2]
        rom_gpu1[11] = 64'h0000000000000000;  // NOP
        rom_gpu1[12] = 64'h0000000000000000;  // NOP
        rom_gpu1[13] = 64'h0000000000000000;  // NOP
        rom_gpu1[14] = 64'h0000000000000000;  // NOP
        rom_gpu1[15] = 64'h1000030000000000;  // GEN  → D[3]
        rom_gpu1[16] = 64'h0000000000000000;  // NOP
        rom_gpu1[17] = 64'h0000000000000000;  // NOP
        rom_gpu1[18] = 64'h0000000000000000;  // NOP
        rom_gpu1[19] = 64'h2E00020003000200;  // COMP D[2]=D[3]+D[2]
        rom_gpu1[20] = 64'h2E00010002000100;  // COMP D[1]=D[2]+D[1]
        rom_gpu1[21] = 64'h3000040001000000;  // SEND dest=D[4]@GPU0, src=D[1]

        // GPU 2: 11 instructions — 2-leaf subtree, SEND to GPU 0
        rom_gpu2[ 0] = 64'h1000010000000000;  // GEN  → D[1]
        rom_gpu2[ 1] = 64'h0000000000000000;  // NOP
        rom_gpu2[ 2] = 64'h0000000000000000;  // NOP
        rom_gpu2[ 3] = 64'h0000000000000000;  // NOP
        rom_gpu2[ 4] = 64'h0000000000000000;  // NOP
        rom_gpu2[ 5] = 64'h1000020000000000;  // GEN  → D[2]
        rom_gpu2[ 6] = 64'h0000000000000000;  // NOP
        rom_gpu2[ 7] = 64'h0000000000000000;  // NOP
        rom_gpu2[ 8] = 64'h0000000000000000;  // NOP
        rom_gpu2[ 9] = 64'h2E00010002000100;  // COMP D[1]=D[2]+D[1]
        rom_gpu2[10] = 64'h3000030001000000;  // SEND dest=D[3]@GPU0, src=D[1]

        // GPU 3: 5 instructions — single leaf, immediate SEND to GPU 0
        rom_gpu3[ 0] = 64'h1000010000000000;  // GEN  → D[1]
        rom_gpu3[ 1] = 64'h0000000000000000;  // NOP
        rom_gpu3[ 2] = 64'h0000000000000000;  // NOP
        rom_gpu3[ 3] = 64'h0000000000000000;  // NOP
        rom_gpu3[ 4] = 64'h3000020001000000;  // SEND dest=D[2]@GPU0, src=D[1]
    end

    // =========================================================================
    // VIO Signals
    // =========================================================================
    logic [63:0] vio_leaf_value;
    logic [3:0]  vio_leaf_idx;
    logic        vio_leaf_wr;
    logic        vio_start_vio;

    logic [63:0] vio_result;
    logic        vio_done;
    logic [NN-1:0] vio_error_all;
    logic [1:0]  vio_error;
    logic [31:0] vio_perf_cycles;
    logic [31:0] vio_perf_stalls;
    logic [7:0]  vio_state;

    assign vio_result      = sys_result;
    assign vio_done        = all_done;
    assign vio_error       = {|sys_error[NN-1:2], |sys_error[1:0]};
    assign vio_perf_cycles = perf_total[0];
    assign vio_perf_stalls = perf_stall[0];

    `ifndef SIMULATION
    u_vio_0 u_vio_inst (
        .clk        (clk),
        .probe_in0  (vio_result),
        .probe_in1  (vio_done),
        .probe_in2  (vio_error),
        .probe_in3  (vio_perf_cycles),
        .probe_in4  (vio_perf_stalls),
        .probe_in5  (vio_state),
        .probe_out0 (vio_leaf_value),
        .probe_out1 (vio_leaf_idx),
        .probe_out2 (vio_leaf_wr),
        .probe_out3 (vio_start_vio)
    );
    `else
    assign vio_start_vio = 1'b0;
    `endif

    // =========================================================================
    // ILA IP (captures GPU 0 & 1 for debug)
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
        .probe0 (ila_gpu0_result),
        .probe1 (ila_gpu1_result),
        .probe2 (ila_gpu0_status),
        .probe3 (ila_gpu1_status)
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
            3'd0: hex_digit = display_value[3:0];   3'd1: hex_digit = display_value[7:4];
            3'd2: hex_digit = display_value[11:8];   3'd3: hex_digit = display_value[15:12];
            3'd4: hex_digit = display_value[19:16];  3'd5: hex_digit = display_value[23:20];
            3'd6: hex_digit = display_value[27:24];  3'd7: hex_digit = display_value[31:28];
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
    // Ring topology adjacency (4 nodes, bidirectional ring):
    //   R0.p1 ↔ R1.p1, R1.p2 ↔ R2.p1, R2.p2 ↔ R3.p1, R3.p2 ↔ R0.p2
    //
    // Leaf assignment (from compiler):
    //   GPU 0: 1 leaf (idx 0) → GCI[0]
    //   GPU 1: 4 leaves (idx 1-4) → GCI[0-3]
    //   GPU 2: 2 leaves (idx 5-6) → GCI[0-1]
    //   GPU 3: 1 leaf (idx 7) → GCI[0]
    // =========================================================================
    typedef enum logic [4:0] {
        S_ADJ0, S_ADJ1, S_ADJ2, S_ADJ3,
        S_ADJ4, S_ADJ5, S_ADJ6, S_ADJ7,
        S_RT,
        S_INSTR0, S_INSTR1, S_INSTR2, S_INSTR3,
        S_SIZE,
        S_WAIT_LEAVES,
        S_START, S_RUN, S_DONE
    } state_t;

    state_t     state;
    logic [5:0] counter;
    // For routing table: iterate over router×destination
    logic [2:0] rt_rtr;
    logic [2:0] rt_dst;
    logic       vio_leaf_wr_prev;
    logic       vio_start_prev;

    assign vio_state = {3'd0, state};

    always_ff @(posedge clk) begin
        if (rst) begin
            state          <= S_ADJ0;
            counter        <= '0;
            rt_rtr         <= '0;
            rt_dst         <= '0;
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
                // ── Ring adjacency: 8 entries (4 bidirectional links) ──
                // R0.p1 ↔ R1.p1
                S_ADJ0: begin adj_wr_en<=1; adj_rtr_id<=0; adj_port_id<=1; adj_target_rtr<=1; adj_target_port<=1; state<=S_ADJ1; end
                S_ADJ1: begin adj_wr_en<=1; adj_rtr_id<=1; adj_port_id<=1; adj_target_rtr<=0; adj_target_port<=1; state<=S_ADJ2; end
                // R1.p2 ↔ R2.p1
                S_ADJ2: begin adj_wr_en<=1; adj_rtr_id<=1; adj_port_id<=2; adj_target_rtr<=2; adj_target_port<=1; state<=S_ADJ3; end
                S_ADJ3: begin adj_wr_en<=1; adj_rtr_id<=2; adj_port_id<=1; adj_target_rtr<=1; adj_target_port<=2; state<=S_ADJ4; end
                // R2.p2 ↔ R3.p1
                S_ADJ4: begin adj_wr_en<=1; adj_rtr_id<=2; adj_port_id<=2; adj_target_rtr<=3; adj_target_port<=1; state<=S_ADJ5; end
                S_ADJ5: begin adj_wr_en<=1; adj_rtr_id<=3; adj_port_id<=1; adj_target_rtr<=2; adj_target_port<=2; state<=S_ADJ6; end
                // R3.p2 ↔ R0.p2 (closes the ring)
                S_ADJ6: begin adj_wr_en<=1; adj_rtr_id<=3; adj_port_id<=2; adj_target_rtr<=0; adj_target_port<=2; state<=S_ADJ7; end
                S_ADJ7: begin adj_wr_en<=1; adj_rtr_id<=0; adj_port_id<=2; adj_target_rtr<=3; adj_target_port<=2; state<=S_RT; rt_rtr<=0; rt_dst<=0; end

                // ── Routing tables (shortest path on ring) ──
                // For 4-node ring: next_hop[r][d] = shortest direction
                // R0: d0→local, d1→p1, d2→p1, d3→p2
                // R1: d0→p1,    d1→local, d2→p2, d3→p1
                // R2: d0→p1,    d1→p1, d2→local, d3→p2
                // R3: d0→p2,    d1→p1, d2→p1, d3→local
                S_RT: begin
                    logic [1:0] nh;
                    case ({rt_rtr, rt_dst})
                        // Router 0
                        6'b000_000: nh = 0;  // R0→d0: local
                        6'b000_001: nh = 1;  // R0→d1: port 1
                        6'b000_010: nh = 1;  // R0→d2: port 1 (via R1)
                        6'b000_011: nh = 2;  // R0→d3: port 2 (wrap)
                        // Router 1
                        6'b001_000: nh = 1;  // R1→d0: port 1
                        6'b001_001: nh = 0;  // R1→d1: local
                        6'b001_010: nh = 2;  // R1→d2: port 2
                        6'b001_011: nh = 1;  // R1→d3: port 1 (via R0, wrap)
                        // Router 2
                        6'b010_000: nh = 1;  // R2→d0: port 1 (via R1)
                        6'b010_001: nh = 1;  // R2→d1: port 1
                        6'b010_010: nh = 0;  // R2→d2: local
                        6'b010_011: nh = 2;  // R2→d3: port 2
                        // Router 3
                        6'b011_000: nh = 2;  // R3→d0: port 2 (wrap)
                        6'b011_001: nh = 1;  // R3→d1: port 1 (via R2)
                        6'b011_010: nh = 1;  // R3→d2: port 1
                        6'b011_011: nh = 0;  // R3→d3: local
                        default:    nh = 0;
                    endcase
                    rtr_rt_wr_en[rt_rtr]  <= 1'b1;
                    rtr_rt_wr_addr[rt_rtr] <= {13'd0, rt_dst};
                    rtr_rt_wr_data[rt_rtr] <= nh;

                    if (rt_dst == 3'd3) begin
                        if (rt_rtr == 3'd3) begin
                            state <= S_INSTR0; counter <= '0;
                        end else begin
                            rt_rtr <= rt_rtr + 1;
                            rt_dst <= 3'd0;
                        end
                    end else begin
                        rt_dst <= rt_dst + 1;
                    end
                end

                // ── Instructions ──
                S_INSTR0: begin
                    imem_wr_en[0] <= 1'b1;
                    imem_wr_addr[0] <= {10'd0, counter};
                    imem_wr_data[0] <= rom_gpu0[counter];
                    if (counter == G0_SZ - 1) begin state <= S_INSTR1; counter <= '0; end
                    else counter <= counter + 1;
                end
                S_INSTR1: begin
                    imem_wr_en[1] <= 1'b1;
                    imem_wr_addr[1] <= {10'd0, counter};
                    imem_wr_data[1] <= rom_gpu1[counter];
                    if (counter == G1_SZ - 1) begin state <= S_INSTR2; counter <= '0; end
                    else counter <= counter + 1;
                end
                S_INSTR2: begin
                    imem_wr_en[2] <= 1'b1;
                    imem_wr_addr[2] <= {10'd0, counter};
                    imem_wr_data[2] <= rom_gpu2[counter];
                    if (counter == G2_SZ - 1) begin state <= S_INSTR3; counter <= '0; end
                    else counter <= counter + 1;
                end
                S_INSTR3: begin
                    imem_wr_en[3] <= 1'b1;
                    imem_wr_addr[3] <= {10'd0, counter};
                    imem_wr_data[3] <= rom_gpu3[counter];
                    if (counter == G3_SZ - 1) state <= S_SIZE;
                    else counter <= counter + 1;
                end

                S_SIZE: begin
                    imem_size[0] <= G0_SZ[15:0];
                    imem_size[1] <= G1_SZ[15:0];
                    imem_size[2] <= G2_SZ[15:0];
                    imem_size[3] <= G3_SZ[15:0];
                    state <= S_WAIT_LEAVES;
                    led <= 8'hAA;
                end

                // ── Wait for VIO leaf loading ──
                S_WAIT_LEAVES: begin
                    led <= 8'hAA;

                    if (vio_leaf_wr && !vio_leaf_wr_prev) begin
                        // Leaf assignment: idx 0→GPU0, idx 1-4→GPU1, idx 5-6→GPU2, idx 7→GPU3
                        if (vio_leaf_idx == 4'd0) begin
                            gci_buf_wr_en[0] <= 1'b1;
                            gci_buf_wr_addr[0] <= 16'd0;
                            gci_buf_wr_data[0] <= vio_leaf_value;
                        end else if (vio_leaf_idx <= 4'd4) begin
                            gci_buf_wr_en[1] <= 1'b1;
                            gci_buf_wr_addr[1] <= {12'd0, vio_leaf_idx - 4'd1};
                            gci_buf_wr_data[1] <= vio_leaf_value;
                        end else if (vio_leaf_idx <= 4'd6) begin
                            gci_buf_wr_en[2] <= 1'b1;
                            gci_buf_wr_addr[2] <= {12'd0, vio_leaf_idx - 4'd5};
                            gci_buf_wr_data[2] <= vio_leaf_value;
                        end else begin
                            gci_buf_wr_en[3] <= 1'b1;
                            gci_buf_wr_addr[3] <= 16'd0;
                            gci_buf_wr_data[3] <= vio_leaf_value;
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
