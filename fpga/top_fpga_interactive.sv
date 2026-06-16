// =============================================================================
// top_fpga_interactive.sv — VIO/ILA Interactive FPGA Wrapper (Nexys A7)
//
// This wrapper combines:
//   1. Hardware bootloader: loads instructions, routing tables, adjacency
//      at reset (same as top_det_g2 config FSM)
//   2. VIO leaf loading: after config, waits for user to enter leaf values
//      and trigger reduction via Vivado Hardware Manager VIO probes
//   3. ILA debug: captures pipeline activity for step-by-step observation
//   4. 7-segment display: shows the reduction result in hex
//   5. Switch trigger: SW[0] can trigger reduction instead of VIO
//
// Configuration: G=2, linear topology, 8-leaf binary tree
//   GPU 0: leaves L0-L3, subtree + root aggregation
//   GPU 1: leaves L4-L7, subtree + SEND result to GPU 0
//
// Usage after bitstream load:
//   1. Set vio_leaf_value to the 64-bit leaf value
//   2. Set vio_leaf_idx to the leaf index (0-7)
//   3. Toggle vio_leaf_wr from 0→1→0 to latch the value
//   4. Repeat for all 8 leaves
//   5. Toggle vio_start from 0→1 OR flip SW[0] to trigger reduction
//   6. Read vio_result and vio_perf_cycles from output probes
//   7. Result displayed on 7-segment display in hex
// =============================================================================
`timescale 1ns / 1ps

module top_fpga_interactive (
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
    localparam int PP = 2;   // 2 ports per router
    localparam int LEAVES_PER_GPU = 4;
    localparam int TOTAL_LEAVES   = NN * LEAVES_PER_GPU;

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
    logic [NR-1:0][0:0]   rtr_rt_wr_data;

    logic                 adj_wr_en;
    logic [11:0]          adj_rtr_id, adj_port_id, adj_target_rtr, adj_target_port;

    logic [NN-1:0]        gci_buf_wr_en;
    logic [NN-1:0][15:0]  gci_buf_wr_addr;
    logic [NN-1:0][63:0]  gci_buf_wr_data;

    logic [NN-1:0][31:0]  perf_total, perf_stall, perf_retired;

    // ── noc_system instance ──
    noc_system #(
        .N_NODES(NN), .N_ROUTERS(NR), .PORTS_PER_RTR(PP),
        .NUM_VCS(2), .GCI_BUF_DEPTH(LEAVES_PER_GPU),
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

    // ── Instruction ROMs ──
    // Each GENERATE must complete before the next fires (gci_pending is single-entry).
    // GCI_LATENCY=4, so 5 NOPs after each GENERATE gives margin for completion.
    // GPU 0: 4×(GEN+5NOP)=24, 3×COMPUTE, RECV, 12×NOP, COMPUTE(root) = 41 instrs
    // GPU 1: 4×(GEN+5NOP)=24, 3×COMPUTE, SEND = 28 instrs
    //
    // COMPUTE aux field is patched at load time using vio_alu_mode.
    // aux = {alu_op[2:0], 1'b0} so aux[3:1] = ALU operation.
    localparam logic [63:0] NOP64 = 64'h0;
    localparam int G0_SZ = 41;
    localparam int G1_SZ = 28;
    logic [63:0] rom_gpu0 [0:G0_SZ-1];
    logic [63:0] rom_gpu1 [0:G1_SZ-1];

    // ALU aux nibble: {alu_op[2:0], link=0}
    // Forward declaration — vio_alu_mode is driven by VIO IP (or testbench force)
    logic [2:0]  vio_alu_mode;
    logic [3:0] compute_aux;
    assign compute_aux = {vio_alu_mode, 1'b0};

    initial begin
        int p;
        // GPU 0: GENERATE with NOPs between each
        p = 0;
        rom_gpu0[p] = {4'h1, 4'h0, 16'd0, 16'd0, 16'd0, 8'd0}; p++; // GEN → D[0]
        for (int i=0;i<5;i++) begin rom_gpu0[p] = NOP64; p++; end
        rom_gpu0[p] = {4'h1, 4'h0, 16'd1, 16'd0, 16'd0, 8'd0}; p++; // GEN → D[1]
        for (int i=0;i<5;i++) begin rom_gpu0[p] = NOP64; p++; end
        rom_gpu0[p] = {4'h1, 4'h0, 16'd2, 16'd0, 16'd0, 8'd0}; p++; // GEN → D[2]
        for (int i=0;i<5;i++) begin rom_gpu0[p] = NOP64; p++; end
        rom_gpu0[p] = {4'h1, 4'h0, 16'd3, 16'd0, 16'd0, 8'd0}; p++; // GEN → D[3]
        for (int i=0;i<5;i++) begin rom_gpu0[p] = NOP64; p++; end
        // p = 24: Compute subtree (aux patched at load time)
        rom_gpu0[p] = {4'h2, 4'h0, 16'd4, 16'd0, 16'd1, 8'd0}; p++; // D[4]=D[0] op D[1]
        rom_gpu0[p] = {4'h2, 4'h0, 16'd5, 16'd2, 16'd3, 8'd0}; p++; // D[5]=D[2] op D[3]
        rom_gpu0[p] = {4'h2, 4'h0, 16'd6, 16'd4, 16'd5, 8'd0}; p++; // D[6]=subtree0
        // p = 27: RECV
        rom_gpu0[p] = {4'h4, 4'h0, 16'd7, 16'd0, 16'd0, 8'd0}; p++; // RECV → D[7]
        // 12 NOPs for packet arrival
        for (int i=0;i<12;i++) begin rom_gpu0[p] = NOP64; p++; end
        // p = 40: Root computation
        rom_gpu0[p] = {4'h2, 4'h0, 16'd8, 16'd6, 16'd7, 8'd0}; // D[8]=ROOT

        // GPU 1
        p = 0;
        rom_gpu1[p] = {4'h1, 4'h0, 16'd0, 16'd0, 16'd0, 8'd0}; p++; // GEN → D[0]
        for (int i=0;i<5;i++) begin rom_gpu1[p] = NOP64; p++; end
        rom_gpu1[p] = {4'h1, 4'h0, 16'd1, 16'd0, 16'd0, 8'd0}; p++; // GEN → D[1]
        for (int i=0;i<5;i++) begin rom_gpu1[p] = NOP64; p++; end
        rom_gpu1[p] = {4'h1, 4'h0, 16'd2, 16'd0, 16'd0, 8'd0}; p++; // GEN → D[2]
        for (int i=0;i<5;i++) begin rom_gpu1[p] = NOP64; p++; end
        rom_gpu1[p] = {4'h1, 4'h0, 16'd3, 16'd0, 16'd0, 8'd0}; p++; // GEN → D[3]
        for (int i=0;i<5;i++) begin rom_gpu1[p] = NOP64; p++; end
        // p = 24: Compute subtree (aux patched at load time)
        rom_gpu1[p] = {4'h2, 4'h0, 16'd4, 16'd0, 16'd1, 8'd0}; p++; // D[4]=D[0] op D[1]
        rom_gpu1[p] = {4'h2, 4'h0, 16'd5, 16'd2, 16'd3, 8'd0}; p++; // D[5]=D[2] op D[3]
        rom_gpu1[p] = {4'h2, 4'h0, 16'd6, 16'd4, 16'd5, 8'd0}; p++; // D[6]=subtree1
        // p = 27: SEND
        rom_gpu1[p] = {4'h3, 4'h0, 16'd6, 16'd6, 16'd0, 8'd0};      // SEND D[6]
    end

    // Patch COMPUTE instructions with selected ALU mode at IMEM load time.
    // If the instruction is a COMPUTE (opcode=0x2), replace aux with compute_aux.
    function automatic logic [63:0] patch_instr(input logic [63:0] raw);
        if (raw[63:60] == 4'h2)
            return {raw[63:60], compute_aux, raw[55:0]};
        else
            return raw;
    endfunction

    // =========================================================================
    // VIO Signals — driven by VIO IP (instantiated via Tcl create_ip)
    //
    // In synthesis: VIO IP module u_vio_0 drives probe_out → these signals
    // In simulation: testbench uses `force` to drive these signals
    // =========================================================================

    // VIO OUTPUT probes (user → FPGA, active in Vivado Hardware Manager)
    logic [63:0] vio_leaf_value;   // probe_out0: 64-bit leaf value to write
    logic [3:0]  vio_leaf_idx;     // probe_out1: which leaf (0-7)
    logic        vio_leaf_wr;      // probe_out2: rising edge = latch value
    logic        vio_start_vio;    // probe_out3: rising edge = start reduction (from VIO)
    // vio_alu_mode declared earlier (before compute_aux assignment)

    // VIO INPUT probes (FPGA → user, read in Vivado Hardware Manager)
    logic [63:0] vio_result;
    logic        vio_done;
    logic [1:0]  vio_error;
    logic [31:0] vio_perf_cycles;
    logic [31:0] vio_perf_stalls;
    logic [7:0]  vio_state;

    // VIO input probe assignments
    assign vio_result      = sys_result;
    assign vio_done        = all_done;
    assign vio_error       = sys_error;
    assign vio_perf_cycles = perf_total[0];
    assign vio_perf_stalls = perf_stall[0];

    // =========================================================================
    // VIO IP Instantiation (module generated by Tcl create_ip)
    //
    // In simulation (no IP available), the testbench uses `force` to drive
    // the vio_* signals directly, and this instantiation is excluded.
    // =========================================================================
    `ifndef SIMULATION
    u_vio_0 u_vio_inst (
        .clk        (clk),
        .probe_in0  (vio_result),       // [63:0] result
        .probe_in1  (vio_done),         // [0:0]  done
        .probe_in2  (vio_error),        // [1:0]  error
        .probe_in3  (vio_perf_cycles),  // [31:0] cycles
        .probe_in4  (vio_perf_stalls),  // [31:0] stalls
        .probe_in5  (vio_state),        // [7:0]  state
        .probe_out0 (vio_leaf_value),   // [63:0] leaf value
        .probe_out1 (vio_leaf_idx),     // [3:0]  leaf index
        .probe_out2 (vio_leaf_wr),      // [0:0]  leaf write
        .probe_out3 (vio_start_vio),    // [0:0]  start (VIO)
        .probe_out4 (vio_alu_mode)      // [2:0]  ALU mode
    );
    `else
    // In simulation, these are driven by testbench `force`
    // No assignment needed — testbench controls these signals
    assign vio_start_vio = 1'b0;  // default, overridden by force
    assign vio_alu_mode  = 3'b000;
    `endif

    // =========================================================================
    // ILA IP Instantiation (module generated by Tcl create_ip)
    //
    // Captures internal pipeline signals for debug observation.
    // =========================================================================
    logic [63:0] ila_gpu0_result;
    logic [63:0] ila_gpu1_result;
    logic [7:0]  ila_gpu0_status;
    logic [7:0]  ila_gpu1_status;

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
    // Switch Debounce + Start Trigger (OR of VIO start and switch)
    // =========================================================================
    logic [2:0]  sw_sync;
    logic        sw_debounced;
    logic        vio_start;     // combined start signal

    always_ff @(posedge clk) sw_sync <= {sw_sync[1:0], sw_start};
    assign sw_debounced = sw_sync[2];

    // Combined start: either VIO or physical switch
    assign vio_start = vio_start_vio | sw_debounced;

    // =========================================================================
    // 7-Segment Display Driver
    //
    // Shows sys_result[31:0] as 8-digit hex on the Nexys A7 7-segment display.
    // Common-anode: segments are active LOW, anodes are active LOW.
    // Multiplexes at ~1kHz (100MHz / 2^17 ≈ 763 Hz).
    // =========================================================================
    logic [31:0] display_value;
    logic [16:0] refresh_counter;  // 17-bit counter for ~763Hz refresh
    logic [2:0]  digit_sel;        // which digit (0-7) is currently active
    logic [3:0]  hex_digit;        // 4-bit hex value for current digit
    logic [6:0]  seg_pattern;      // segment pattern (active HIGH, inverted at output)

    // Latch result when done
    always_ff @(posedge clk) begin
        if (rst)
            display_value <= 32'd0;
        else if (all_done)
            display_value <= sys_result[31:0];
    end

    // Refresh counter
    always_ff @(posedge clk) begin
        if (rst)
            refresh_counter <= 17'd0;
        else
            refresh_counter <= refresh_counter + 17'd1;
    end

    assign digit_sel = refresh_counter[16:14];

    // Digit multiplexer: select which 4-bit nibble to display
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

    // Hex-to-7-segment decoder (active HIGH encoding)
    //   Segment order: seg[6:0] = {CG, CF, CE, CD, CC, CB, CA}
    //
    //     AAA
    //    F   B
    //     GGG
    //    E   C
    //     DDD
    always_comb begin
        case (hex_digit)
            //                    GFEDCBA
            4'h0: seg_pattern = 7'b0111111;
            4'h1: seg_pattern = 7'b0000110;
            4'h2: seg_pattern = 7'b1011011;
            4'h3: seg_pattern = 7'b1001111;
            4'h4: seg_pattern = 7'b1100110;
            4'h5: seg_pattern = 7'b1101101;
            4'h6: seg_pattern = 7'b1111101;
            4'h7: seg_pattern = 7'b0000111;
            4'h8: seg_pattern = 7'b1111111;
            4'h9: seg_pattern = 7'b1101111;
            4'hA: seg_pattern = 7'b1110111;
            4'hB: seg_pattern = 7'b1111100;
            4'hC: seg_pattern = 7'b0111001;
            4'hD: seg_pattern = 7'b1011110;
            4'hE: seg_pattern = 7'b1111001;
            4'hF: seg_pattern = 7'b1110001;
        endcase
    end

    // Output: invert for active-low cathodes
    assign seg = ~seg_pattern;
    assign dp  = 1'b1;  // decimal point off (active low)

    // Anode control: only enable the selected digit (active low)
    always_comb begin
        an = 8'hFF;  // all off
        if (all_done)
            an[digit_sel] = 1'b0;  // enable selected digit
    end

    // =========================================================================
    // Config FSM + Leaf Loading + Start Control
    //
    // States:
    //   S_ADJ   → S_RT   → S_INSTR  → S_SIZE → S_WAIT_LEAVES:
    //     (hardware bootloader — runs once after reset)
    //   S_WAIT_LEAVES:
    //     Waits for user to load leaf values via VIO and toggle vio_start
    //   S_START → S_RUN → S_DONE:
    //     Triggers reduction, waits for completion
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
                // ── Hardware Bootloader: Adjacency ──
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

                // ── Hardware Bootloader: Routing Tables ──
                S_RT0: begin rtr_rt_wr_en[0]<=1; rtr_rt_wr_addr[0]<=0; rtr_rt_wr_data[0]<=0; state<=S_RT1; end
                S_RT1: begin rtr_rt_wr_en[0]<=1; rtr_rt_wr_addr[0]<=1; rtr_rt_wr_data[0]<=1; state<=S_RT2; end
                S_RT2: begin rtr_rt_wr_en[1]<=1; rtr_rt_wr_addr[1]<=0; rtr_rt_wr_data[1]<=1; state<=S_RT3; end
                S_RT3: begin rtr_rt_wr_en[1]<=1; rtr_rt_wr_addr[1]<=1; rtr_rt_wr_data[1]<=0; state<=S_INSTR_GPU0; counter<='0; end

                // ── Hardware Bootloader: Instructions ──
                S_INSTR_GPU0: begin
                    imem_wr_en[0]   <= 1'b1;
                    imem_wr_addr[0] <= {11'd0, counter};
                    imem_wr_data[0] <= patch_instr(rom_gpu0[counter]);
                    if (counter == G0_SZ - 1) begin state <= S_INSTR_GPU1; counter <= '0; end
                    else counter <= counter + 1;
                end
                S_INSTR_GPU1: begin
                    imem_wr_en[1]   <= 1'b1;
                    imem_wr_addr[1] <= {11'd0, counter};
                    imem_wr_data[1] <= patch_instr(rom_gpu1[counter]);
                    if (counter == G1_SZ - 1) state <= S_SIZE;
                    else counter <= counter + 1;
                end

                S_SIZE: begin
                    imem_size[0] <= G0_SZ[15:0];
                    imem_size[1] <= G1_SZ[15:0];
                    state <= S_WAIT_LEAVES;
                    led <= 8'hAA;  // pattern = "waiting for leaves"
                end

                // ── Wait for VIO leaf loading ──
                // User enters leaf values via VIO probes in Vivado Hardware Manager
                // Toggle vio_leaf_wr to write each value, then toggle vio_start
                S_WAIT_LEAVES: begin
                    led <= 8'hAA;  // visual indicator: waiting for input

                    // Rising edge of vio_leaf_wr → latch leaf value to GCI buffer
                    if (vio_leaf_wr && !vio_leaf_wr_prev) begin
                        // Map global leaf index to (node, local_index)
                        // Leaves 0-3 → GPU 0, buffer[0-3]
                        // Leaves 4-7 → GPU 1, buffer[0-3]
                        if (vio_leaf_idx < LEAVES_PER_GPU) begin
                            gci_buf_wr_en[0]   <= 1'b1;
                            gci_buf_wr_addr[0] <= {12'd0, vio_leaf_idx};
                            gci_buf_wr_data[0] <= vio_leaf_value;
                        end else begin
                            gci_buf_wr_en[1]   <= 1'b1;
                            gci_buf_wr_addr[1] <= {12'd0, vio_leaf_idx - LEAVES_PER_GPU[3:0]};
                            gci_buf_wr_data[1] <= vio_leaf_value;
                        end
                    end

                    // Rising edge of vio_start → trigger reduction
                    if (vio_start && !vio_start_prev) begin
                        state <= S_START;
                    end
                end

                // ── Run Reduction ──
                S_START: begin
                    program_start <= 1'b1;
                    led <= 8'h55;  // pattern = "running"
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
                    // Can reset via btn_rst to re-run with new values
                end

                default: ;
            endcase
        end
    end

endmodule
