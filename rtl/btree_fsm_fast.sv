// =============================================================================
// btree_fsm_fast.sv — 3-Stage Pipelined Per-GPU Reduction FSM v5.0
//
// DROP-IN REPLACEMENT for btree_fsm.sv (identical port interface)
//
// Pipeline:   IF ──► DE ──► EX
//             │       │       │
//           IMEM   DMEM_rd  ALU/SEND/WB
//
// v8.0 RDMA-Push Architecture:
//   ● 3-stage pipeline: 1 instruction/cycle throughput
//   ● Non-blocking SEND: enqueue-and-continue, stall only if TX FIFO full
//   ● RDMA-Push PIU: autonomous packet→DMEM write using target_addr from pkt
//   ● DMEM scoreboard: tracks which addresses have valid data
//   ● Non-blocking GENERATE: same as v4.1, with hazard interlock
//   ● Scoreboard hazard detection: DE stalls if reading unwritten DMEM addr
//   ● 1-level DMEM write→read forwarding (covers back-to-back COMPUTE)
//
// Preserved:
//   ● Same 64-bit ISA, 96-bit packets, credit-based flow control
//   ● Independent PIU (Packet Ingress Unit) for deadlock prevention
//   ● 3-way DMEM write arbitration: PIU > GCI > FSM
//   ● Performance counters, watchdog, timeout
//
// Stall conditions (pipeline freezes from stall point backward):
//   EX stall: SEND with full TX FIFO, or DMEM write collision
//   DE stall: EX stall, or scoreboard hazard (reading addr with scoreboard=0)
//   IF stall: DE stall
// =============================================================================
`timescale 1ns / 1ps

import btree_pkg::*;

module btree_fsm_fast #(
    parameter int NUM_LINKS    = 2,
    parameter int TX_BUF_DEPTH = 8,
    parameter int RX_BUF_DEPTH = 8,
    parameter int DMEM_DEPTH   = 512,
    parameter int IMEM_DEPTH   = 512,
    parameter int TIMEOUT_MAX  = 10000,
    parameter int WATCHDOG_MAX = 20000
)(
    input  logic        clk,
    input  logic        rst,
    input  logic [15:0] gpu_id,
    // Program control
    input  logic        program_start,
    output logic        done,
    output logic [7:0]  status,
    output logic [63:0] result,
    output logic        error,
    // Instruction memory loading
    input  logic        imem_wr_en,
    input  logic [15:0] imem_wr_addr,
    input  logic [63:0] imem_wr_data,
    input  logic [15:0] imem_size,
    // GCI interface
    output logic        gci_start,
    output logic [15:0] gci_dest_addr,
    input  logic        gci_done,
    input  logic [63:0] gci_result,
    // Error diagnostics
    output logic [15:0] error_pc,
    output logic [3:0]  error_state,
    // Performance counters
    output logic [31:0] perf_total_cycles,
    output logic [31:0] perf_stall_cycles,
    output logic [31:0] perf_instr_retired,
    // Link interfaces (96-bit, credit-based)
    input  logic [NUM_LINKS-1:0]        link_rx_valid,
    input  logic [NUM_LINKS-1:0][95:0]  link_rx_data,
    output logic [NUM_LINKS-1:0]        link_tx_valid,
    output logic [NUM_LINKS-1:0][95:0]  link_tx_data,
    input  logic [NUM_LINKS-1:0]        link_credit_in,
    output logic [NUM_LINKS-1:0]        link_credit_out,
    // Routing table config
    input  logic                        rt_wr_en,
    input  logic [11:0]                 rt_wr_addr,
    input  logic [$clog2(NUM_LINKS)-1:0] rt_wr_data
);

    localparam int DMEM_ADDR_W = $clog2(DMEM_DEPTH);
    localparam int IMEM_ADDR_W = $clog2(IMEM_DEPTH);
    localparam int LINK_W      = $clog2(NUM_LINKS) > 0 ? $clog2(NUM_LINKS) : 1;

    // =========================================================================
    // Pipeline State Machine
    // =========================================================================
    typedef enum logic [2:0] {
        P_IDLE  = 3'd0,
        P_RUN   = 3'd1,
        P_DRAIN = 3'd2,   // IF done, waiting for pipeline to empty
        P_DONE  = 3'd3,
        P_ERROR = 3'd4
    } pipe_state_t;

    pipe_state_t pstate;

    // =========================================================================
    // Clock Gating: gate memory/FIFO operations when node is idle/done/error
    // This reduces dynamic power for inactive nodes in large configurations.
    // =========================================================================
    logic pipeline_active;
    assign pipeline_active = (pstate == P_RUN || pstate == P_DRAIN);

    // =========================================================================
    // IMEM (inlined — IFU's stall-clears-valid behavior is incompatible
    // with pipeline hold semantics, so we manage PC/fetch directly)
    // =========================================================================
    logic [63:0] imem [0:IMEM_DEPTH-1];
    logic [15:0] pc;
    logic        pc_at_end;

    assign pc_at_end = (pc >= imem_size);

    always_ff @(posedge clk) begin
        if (imem_wr_en)
            imem[imem_wr_addr[IMEM_ADDR_W-1:0]] <= imem_wr_data;
    end

    initial begin
        for (int i = 0; i < IMEM_DEPTH; i++)
            imem[i] = 64'd0;
    end

    // =========================================================================
    // DMEM — Dual read + single write + 2-level forwarding
    // =========================================================================
    logic [63:0] dmem [0:DMEM_DEPTH-1];
    logic [63:0] dmem_rd_data_a_raw, dmem_rd_data_b_raw;
    logic [63:0] dmem_rd_data_a, dmem_rd_data_b;
    logic [DMEM_ADDR_W-1:0] dmem_rd_addr_a, dmem_rd_addr_b;
    logic        dmem_wr_en;
    logic [DMEM_ADDR_W-1:0] dmem_wr_addr;
    logic [63:0] dmem_wr_data;

    // Registered read addresses (for forwarding comparison)
    logic [DMEM_ADDR_W-1:0] dmem_rd_addr_a_r, dmem_rd_addr_b_r;

    // Previous-cycle write capture (for pipeline forwarding)
    logic        dmem_wr_en_d1;
    logic [DMEM_ADDR_W-1:0] dmem_wr_addr_d1;
    logic [63:0] dmem_wr_data_d1;
    // 2nd-level capture (survives 1-cycle stalls)
    logic        dmem_wr_en_d2;
    logic [DMEM_ADDR_W-1:0] dmem_wr_addr_d2;
    logic [63:0] dmem_wr_data_d2;

    always_ff @(posedge clk) begin
        dmem_rd_data_a_raw <= dmem[dmem_rd_addr_a];
        dmem_rd_data_b_raw <= dmem[dmem_rd_addr_b];
        dmem_rd_addr_a_r   <= dmem_rd_addr_a;
        dmem_rd_addr_b_r   <= dmem_rd_addr_b;
        if (dmem_wr_en)
            dmem[dmem_wr_addr] <= dmem_wr_data;
        // Capture write for next-cycle forwarding
        dmem_wr_en_d1   <= dmem_wr_en;
        dmem_wr_addr_d1 <= dmem_wr_addr;
        dmem_wr_data_d1 <= dmem_wr_data;
        // 2nd-level capture
        dmem_wr_en_d2   <= dmem_wr_en_d1;
        dmem_wr_addr_d2 <= dmem_wr_addr_d1;
        dmem_wr_data_d2 <= dmem_wr_data_d1;
    end

    // 2-Level Write→Read Forwarding:
    //   Level 1: Previous-cycle write (covers EX(N) writing, DE(N+1) reading
    //            same address — the BRAM read-first gives stale data, so we
    //            forward from the registered write capture)
    //   Level 2: 2-cycles-ago write (covers the case where a 1-cycle stall
    //            occurs between the writer and reader, causing the d1 data
    //            to expire before the read completes)
    assign dmem_rd_data_a =
        (dmem_wr_en_d1 && dmem_wr_addr_d1 == dmem_rd_addr_a_r) ? dmem_wr_data_d1 :
        (dmem_wr_en_d2 && dmem_wr_addr_d2 == dmem_rd_addr_a_r) ? dmem_wr_data_d2 :
        dmem_rd_data_a_raw;

    assign dmem_rd_data_b =
        (dmem_wr_en_d1 && dmem_wr_addr_d1 == dmem_rd_addr_b_r) ? dmem_wr_data_d1 :
        (dmem_wr_en_d2 && dmem_wr_addr_d2 == dmem_rd_addr_b_r) ? dmem_wr_data_d2 :
        dmem_rd_data_b_raw;

    initial begin
        for (int i = 0; i < DMEM_DEPTH; i++)
            dmem[i] = 64'd0;
    end

    // =========================================================================
    // TX FIFOs + TX Controllers (credit-only, per link) — UNCHANGED
    // =========================================================================
    logic [95:0]  txf_w_data  [0:NUM_LINKS-1];
    logic         txf_w_en    [0:NUM_LINKS-1];
    logic         txf_w_rdy   [0:NUM_LINKS-1];
    logic [95:0]  txf_r_data  [0:NUM_LINKS-1];
    logic         txf_r_en    [0:NUM_LINKS-1];
    logic         txf_r_rdy   [0:NUM_LINKS-1];
    logic         txc_send_rdy [0:NUM_LINKS-1];

    // RX FIFOs
    logic [95:0]  rxf_w_data  [0:NUM_LINKS-1];
    logic         rxf_w_en    [0:NUM_LINKS-1];
    logic         rxf_w_rdy   [0:NUM_LINKS-1];
    logic [95:0]  rxf_r_data  [0:NUM_LINKS-1];
    logic         rxf_r_en    [0:NUM_LINKS-1];
    logic         rxf_r_rdy   [0:NUM_LINKS-1];

    genvar gi;
    generate
        for (gi = 0; gi < NUM_LINKS; gi++) begin : gen_link
            sync_fifo #(.WIDTH(96), .DEPTH(TX_BUF_DEPTH)) u_txf (
                .clk(clk), .rst(rst),
                .w_data(txf_w_data[gi]), .w_en(txf_w_en[gi]), .w_rdy(txf_w_rdy[gi]),
                .r_data(txf_r_data[gi]), .r_en(txf_r_en[gi]), .r_rdy(txf_r_rdy[gi]),
                .level()
            );

            sync_fifo #(.WIDTH(96), .DEPTH(RX_BUF_DEPTH)) u_rxf (
                .clk(clk), .rst(rst),
                .w_data(rxf_w_data[gi]), .w_en(rxf_w_en[gi]), .w_rdy(rxf_w_rdy[gi]),
                .r_data(rxf_r_data[gi]), .r_en(rxf_r_en[gi]), .r_rdy(rxf_r_rdy[gi]),
                .level()
            );

            link_tx #(.RX_BUF_DEPTH(RX_BUF_DEPTH)) u_txc (
                .clk(clk), .rst(rst),
                .send_en(txf_r_rdy[gi]),
                .send_data(txf_r_data[gi]),
                .send_rdy(txc_send_rdy[gi]),
                .tx_valid(link_tx_valid[gi]),
                .tx_data(link_tx_data[gi]),
                .credit_return(link_credit_in[gi])
            );

            assign txf_r_en[gi] = txf_r_rdy[gi] && txc_send_rdy[gi];

            assign rxf_w_data[gi] = link_rx_data[gi];
            assign rxf_w_en[gi]   = link_rx_valid[gi] && rxf_w_rdy[gi];
        end
    endgenerate

    // =========================================================================
    // Packet Ingress Unit (PIU) — v8.0 RDMA-Push (autonomous write)
    // Drains RX FIFOs, writes payload directly to DMEM[target_addr].
    // target_addr is extracted from packet[79:70].
    // Sets scoreboard bit on write. No RECV instruction needed.
    // =========================================================================
    logic                       piu_active;
    logic [LINK_W-1:0]          piu_src_link;
    logic [95:0]                piu_pkt;

    logic        piu_dmem_wr;
    logic [DMEM_ADDR_W-1:0] piu_dmem_addr;
    logic [63:0] piu_dmem_data;

    // Misroute detection (should never fire with correct routing tables)
    logic        piu_misroute;

    logic        piu_credit_return [0:NUM_LINKS-1];

    // ── DMEM Scoreboard: tracks which addresses have valid data ──
    // Set by: PIU write, GCI completion, COMPUTE writeback, GENERATE
    // Checked by: DE stage before advancing COMPUTE/SEND
    // Reset on: rst or program_start
    logic [DMEM_DEPTH-1:0] scoreboard;

    // PIU — RX link selection (fixed priority, same as v4.1)
    logic                piu_rx_selected;
    logic [LINK_W-1:0]  piu_rx_link;

    always_comb begin
        piu_rx_selected = 1'b0;
        piu_rx_link     = '0;
        for (int i = NUM_LINKS-1; i >= 0; i--) begin
            if (rxf_r_rdy[i]) begin
                piu_rx_selected = 1'b1;
                piu_rx_link     = i[LINK_W-1:0];
            end
        end
    end

    // PIU sequential — RDMA-Push: autonomous packet → DMEM write
    always_ff @(posedge clk) begin
        if (rst) begin
            piu_active   <= 1'b0;
            piu_src_link <= '0;
            piu_pkt      <= 96'd0;
            piu_misroute <= 1'b0;
            for (int i = 0; i < NUM_LINKS; i++)
                piu_credit_return[i] <= 1'b0;
        end else begin
            for (int i = 0; i < NUM_LINKS; i++)
                piu_credit_return[i] <= 1'b0;
            piu_misroute <= 1'b0;

            if (!piu_active) begin
                if (piu_rx_selected) begin
                    piu_active   <= 1'b1;
                    piu_src_link <= piu_rx_link;
                    piu_pkt      <= rxf_r_data[piu_rx_link];
                end
            end else begin
                if (piu_pkt[95:80] == gpu_id) begin
                    // Packet for this GPU — write directly to DMEM[target_addr]
                    // Trace is opt-in (-d NOC_TRACE): on large configurations
                    // one line per delivered packet per GPU dominates runtime.
                    // Only the $display is gated; the state updates below are
                    // functional and always execute.
`ifdef NOC_TRACE
                    $display("[PIU] %0t | GPU %0d RX: pkt=%0h -> DMEM[%0d]",
                             $time, gpu_id, piu_pkt, piu_pkt[79:70]);
`endif
                    piu_active <= 1'b0;
                    piu_credit_return[piu_src_link] <= 1'b1;
                end else begin
                    // Misrouted packet — drop and flag
                    piu_active   <= 1'b0;
                    piu_misroute <= 1'b1;
                    piu_credit_return[piu_src_link] <= 1'b1;
                end
            end
        end
    end

    // PIU combinational outputs — extract target_addr from packet
    always_comb begin
        automatic logic [NUM_LINKS-1:0] v_rxf_r_en = '0;

        piu_dmem_wr   = 1'b0;
        piu_dmem_addr = '0;
        piu_dmem_data = 64'd0;

        if (!piu_active && piu_rx_selected)
            v_rxf_r_en[piu_rx_link] = 1'b1;

        if (piu_active && piu_pkt[95:80] == gpu_id) begin
            piu_dmem_wr   = 1'b1;
            piu_dmem_addr = piu_pkt[79:70];   // target_addr from packet
            piu_dmem_data = piu_pkt[63:0];    // payload
        end

        for (int i = 0; i < NUM_LINKS; i++) begin
            rxf_r_en[i] = v_rxf_r_en[i];
        end
    end

    // Credit output
    generate
        for (gi = 0; gi < NUM_LINKS; gi++) begin : gen_credit_out
            assign link_credit_out[gi] = piu_credit_return[gi];
        end
    endgenerate

    // =========================================================================
    // DMEM Write Arbitration: PIU > GCI > FSM (UNCHANGED priority)
    // =========================================================================
    logic        fsm_dmem_wr;
    logic [DMEM_ADDR_W-1:0] fsm_dmem_addr;
    logic [63:0] fsm_dmem_data;

    logic        gci_dmem_wr;
    logic [DMEM_ADDR_W-1:0] gci_dmem_addr;
    logic [63:0] gci_dmem_data;

    always_comb begin
        if (piu_dmem_wr) begin
            dmem_wr_en   = 1'b1;
            dmem_wr_addr = piu_dmem_addr;
            dmem_wr_data = piu_dmem_data;
        end else if (gci_dmem_wr) begin
            dmem_wr_en   = 1'b1;
            dmem_wr_addr = gci_dmem_addr;
            dmem_wr_data = gci_dmem_data;
        end else if (fsm_dmem_wr) begin
            dmem_wr_en   = 1'b1;
            dmem_wr_addr = fsm_dmem_addr;
            dmem_wr_data = fsm_dmem_data;
        end else begin
            dmem_wr_en   = 1'b0;
            dmem_wr_addr = '0;
            dmem_wr_data = 64'd0;
        end
    end

    // TX FIFO write: FSM send only (PIU relay removed in v6)
    logic        fsm_txf_en;
    logic [LINK_W-1:0] fsm_txf_link;
    logic [95:0] fsm_txf_data;

    always_comb begin
        automatic logic [NUM_LINKS-1:0] v_txf_w_en = '0;
        automatic logic [95:0]          v_txf_w_data [NUM_LINKS];

        for (int i = 0; i < NUM_LINKS; i++) begin
            v_txf_w_data[i] = 96'd0;
        end

        if (fsm_txf_en) begin
            v_txf_w_en[fsm_txf_link]   = 1'b1;
            v_txf_w_data[fsm_txf_link] = fsm_txf_data;
        end

        for (int i = 0; i < NUM_LINKS; i++) begin
            txf_w_en[i]   = v_txf_w_en[i];
            txf_w_data[i] = v_txf_w_data[i];
        end
    end

    // =========================================================================
    // GCI Completion → DMEM write (with PIU collision retry)
    // =========================================================================
    // Bug fix: When gci_done fires on the same cycle as piu_dmem_wr, the
    // DMEM arbiter drops the GCI write (PIU has higher priority). Without
    // retry logic, gci_pending would clear and gci_rd_ptr would have already
    // advanced, permanently losing the leaf value.
    // Fix: gci_write_held latches a missed write and keeps asserting
    // gci_dmem_wr until the arbiter accepts it (no PIU contention).
    logic        gci_pending;
    logic [15:0] gci_pend_addr;
    logic        gci_write_held;  // retry latch for PIU-blocked GCI writes

    assign gci_dmem_wr   = gci_pending && (gci_done || gci_write_held);
    assign gci_dmem_addr = gci_pend_addr[DMEM_ADDR_W-1:0];
    assign gci_dmem_data = gci_result;

    // =========================================================================
    // ██████╗ ██╗██████╗ ███████╗██╗     ██╗███╗   ██╗███████╗
    // ██╔══██╗██║██╔══██╗██╔════╝██║     ██║████╗  ██║██╔════╝
    // ██████╔╝██║██████╔╝█████╗  ██║     ██║██╔██╗ ██║█████╗
    // ██╔═══╝ ██║██╔═══╝ ██╔══╝  ██║     ██║██║╚██╗██║██╔══╝
    // ██║     ██║██║     ███████╗███████╗██║██║ ╚████║███████╗
    // ╚═╝     ╚═╝╚═╝     ╚══════╝╚══════╝╚═╝╚═╝  ╚═══╝╚══════╝
    // =========================================================================

    // --- IF/DE Pipeline Register ---
    logic        de_valid;
    logic [3:0]  de_opcode, de_aux;
    logic [15:0] de_dest, de_addr_a, de_addr_b;
    logic [15:0] de_pc;   // for error reporting

    // --- DE/EX Pipeline Register ---
    logic        ex_valid;
    logic [3:0]  ex_opcode, ex_aux;
    logic [15:0] ex_dest, ex_addr_a, ex_addr_b;
    logic [15:0] ex_pc;
    // Latched DMEM read data for EX stage (survives stalls)
    logic [63:0] ex_operand_a, ex_operand_b;

    // --- IF Stage: IMEM Fetch ---
    logic [63:0] if_instr;
    logic        if_valid;

    // Forward declarations for pipeline control (defined later in Hazard Detection)
    logic ex_advance, de_advance, if_advance;

    // Registered IMEM read (1-cycle latency, BRAM-compatible)
    always_ff @(posedge clk) begin
        if (rst) begin
            if_valid <= 1'b0;
            if_instr <= 64'd0;
        end else if (if_advance) begin
            if (pstate == P_RUN && !pc_at_end) begin
                if_instr <= imem[pc[IMEM_ADDR_W-1:0]];
                if_valid <= 1'b1;
            end else begin
                if_valid <= 1'b0;
            end
        end
        // When stalled (!if_advance): hold if_valid and if_instr
    end

    // PC management
    always_ff @(posedge clk) begin
        if (rst) begin
            pc <= 16'd0;
        end else if (pstate == P_IDLE && program_start) begin
            pc <= 16'd0;
        end else if (if_advance && pstate == P_RUN && !pc_at_end) begin
            pc <= pc + 16'd1;
        end
    end

    // IF instruction decode (combinational from registered fetch)
    logic [3:0]  if_opcode, if_aux;
    logic [15:0] if_dest, if_addr_a, if_addr_b;

    assign if_opcode = if_instr[63:60];
    assign if_aux    = if_instr[59:56];
    assign if_dest   = if_instr[55:40];
    assign if_addr_a = if_instr[39:24];
    assign if_addr_b = if_instr[23:8];

    // =========================================================================
    // Hazard Detection & Pipeline Control
    // =========================================================================

    // EX stalls: SEND backpressure or DMEM write collision
    logic ex_send_blocked;
    assign ex_send_blocked = ex_valid && ex_opcode == 4'h3 &&
        !txf_w_rdy[ex_aux[LINK_W-1:0]];

    logic ex_gci_blocked;
    assign ex_gci_blocked = ex_valid && ex_opcode == 4'h1 && gci_pending;

    // DMEM write arbitration stall (PIU > GCI > FSM).
    logic ex_dmem_collision;
    assign ex_dmem_collision = ex_valid && (ex_opcode == 4'h2) && (piu_dmem_wr || gci_dmem_wr);

    logic ex_stall;
    assign ex_stall = ex_send_blocked || ex_gci_blocked || ex_dmem_collision;

    // ── Scoreboard-based DE hazard detection ──
    // DE stalls if a COMPUTE or SEND tries to read a DMEM address whose
    // scoreboard bit is 0 (data not yet written by PIU/GCI/COMPUTE).
    logic scoreboard_hazard;
    assign scoreboard_hazard = de_valid && (
        (de_opcode == 4'h2 &&  // COMPUTE reads addr_a and addr_b
            (!scoreboard[de_addr_a[DMEM_ADDR_W-1:0]] ||
             !scoreboard[de_addr_b[DMEM_ADDR_W-1:0]])) ||
        (de_opcode == 4'h3 &&  // SEND reads addr_a only
            !scoreboard[de_addr_a[DMEM_ADDR_W-1:0]])
    );

    // GCI hazard: belt-and-suspenders with scoreboard (catches in-flight GCI)
    logic gci_data_hazard;
    assign gci_data_hazard = de_valid && (
        (gci_pending && (
            (de_opcode == 4'h2 && (de_addr_a[DMEM_ADDR_W-1:0] == gci_pend_addr[DMEM_ADDR_W-1:0] || de_addr_b[DMEM_ADDR_W-1:0] == gci_pend_addr[DMEM_ADDR_W-1:0])) ||
            (de_opcode == 4'h3 && de_addr_a[DMEM_ADDR_W-1:0] == gci_pend_addr[DMEM_ADDR_W-1:0])
        )) ||
        (gci_start && (
            (de_opcode == 4'h2 && (de_addr_a[DMEM_ADDR_W-1:0] == gci_dest_addr[DMEM_ADDR_W-1:0] || de_addr_b[DMEM_ADDR_W-1:0] == gci_dest_addr[DMEM_ADDR_W-1:0])) ||
            (de_opcode == 4'h3 && de_addr_a[DMEM_ADDR_W-1:0] == gci_dest_addr[DMEM_ADDR_W-1:0])
        ))
    );

    logic de_hazard;
    assign de_hazard = scoreboard_hazard || gci_data_hazard;

    // Pipeline advance signals
    assign ex_advance = !ex_stall;
    assign de_advance = ex_advance && !de_hazard;
    assign if_advance = de_advance;

    // =========================================================================
    // DE Stage: Decode + Issue DMEM Reads
    // =========================================================================

    // DMEM read addresses: normally from DE, but re-read EX's addresses when EX stalls
    always_comb begin
        if (ex_stall && ex_valid) begin
            // EX stalled — re-read the stalled instruction's operand addresses
            dmem_rd_addr_a = ex_addr_a[DMEM_ADDR_W-1:0];
            dmem_rd_addr_b = ex_addr_b[DMEM_ADDR_W-1:0];
        end else begin
            dmem_rd_addr_a = de_valid ? de_addr_a[DMEM_ADDR_W-1:0] : '0;
            dmem_rd_addr_b = de_valid ? de_addr_b[DMEM_ADDR_W-1:0] : '0;
        end
    end

    // =========================================================================
    // EX Stage: Execute + Writeback (combinational ALU, single cycle)
    // =========================================================================

    // Inline combinational ALU (eliminates module boundary for pipeline)
    logic [63:0] alu_result_comb;
    logic [2:0]  ex_alu_op;
    assign ex_alu_op = ex_aux[3:1];

    // EX operand mux: use latched values when EX is stalled (DE has moved on)
    logic [63:0] ex_data_a, ex_data_b;
    assign ex_data_a = ex_advance ? dmem_rd_data_a : ex_operand_a;
    assign ex_data_b = ex_advance ? dmem_rd_data_b : ex_operand_b;

    // FP64 adder instance (combinational)
    logic [63:0] fp_add_result;
    fp64_add u_fp_add (
        .a     (ex_data_a),
        .b     (ex_data_b),
        .result(fp_add_result)
    );

    always_comb begin
        case (ex_alu_op)
            3'b000:  alu_result_comb = ex_data_a + ex_data_b;           // ADD (unsigned)
            3'b001:  alu_result_comb = ($signed(ex_data_a) > $signed(ex_data_b))
                                       ? ex_data_a : ex_data_b;          // MAX (signed)
            3'b010:  alu_result_comb = ($signed(ex_data_a) < $signed(ex_data_b))
                                       ? ex_data_a : ex_data_b;          // MIN (signed)
            3'b011:  alu_result_comb = ex_data_a & ex_data_b;           // AND
            3'b100:  alu_result_comb = ex_data_a | ex_data_b;           // OR
            3'b101:  alu_result_comb = ex_data_a ^ ex_data_b;           // XOR
            3'b110:  alu_result_comb = ex_data_a + ex_data_b;           // SADD (signed — same binary op as ADD)
            3'b111:  alu_result_comb = fp_add_result;                              // FADD (IEEE 754 FP64)
            default: alu_result_comb = ex_data_a + ex_data_b;
        endcase
    end

    // EX combinational outputs
    always_comb begin
        fsm_dmem_wr   = 1'b0;
        fsm_dmem_addr = '0;
        fsm_dmem_data = 64'd0;
        fsm_txf_en    = 1'b0;
        fsm_txf_link  = '0;
        fsm_txf_data  = 96'd0;
        gci_start     = 1'b0;
        gci_dest_addr = 16'd0;

        if (ex_valid && ex_advance) begin
            case (ex_opcode)
                4'h0: ; // NOP — nothing

                4'h1: begin // GENERATE — kick GCI (non-blocking)
                    gci_start     = 1'b1;
                    gci_dest_addr = ex_dest;
                end

                4'h2: begin // COMPUTE — ALU result → DMEM writeback
                    fsm_dmem_wr   = 1'b1;
                    fsm_dmem_addr = ex_dest[DMEM_ADDR_W-1:0];
                    fsm_dmem_data = alu_result_comb;
                end

                4'h3: begin // SEND — enqueue packet to TX FIFO (RDMA-Push)
                    if (txf_w_rdy[ex_aux[LINK_W-1:0]]) begin
                        fsm_txf_en   = 1'b1;
                        fsm_txf_link = ex_aux[LINK_W-1:0];
                        // v8.0: [95:80]=dest_gpu, [79:70]=target_addr, [69:64]=0, [63:0]=data
                        fsm_txf_data = {ex_addr_b, ex_dest[9:0], 6'b0, ex_data_a};
                    end
                end

                // 4'h4: OP_RESERVED (was RECV) — falls through to default

                default: ; // Invalid — handled in sequential block
            endcase
        end
    end

    // =========================================================================
    // Pipeline Registers — Sequential Update
    // =========================================================================
    always_ff @(posedge clk) begin
        if (rst) begin
            de_valid   <= 1'b0;
            de_opcode  <= 4'd0;
            de_aux     <= 4'd0;
            de_dest    <= 16'd0;
            de_addr_a  <= 16'd0;
            de_addr_b  <= 16'd0;
            de_pc      <= 16'd0;
            ex_valid   <= 1'b0;
            ex_opcode  <= 4'd0;
            ex_aux     <= 4'd0;
            ex_dest    <= 16'd0;
            ex_addr_a  <= 16'd0;
            ex_addr_b  <= 16'd0;
            ex_pc      <= 16'd0;
        end else begin
            // --- DE/EX register update ---
            if (ex_advance) begin
                if (de_advance && de_valid) begin
                    // DE → EX transfer
                    ex_valid   <= 1'b1;
                    ex_opcode  <= de_opcode;
                    ex_aux     <= de_aux;
                    ex_dest    <= de_dest;
                    ex_addr_a  <= de_addr_a;
                    ex_addr_b  <= de_addr_b;
                    ex_pc      <= de_pc;
                    // Latch DMEM read data for stall survival
                    ex_operand_a <= dmem_rd_data_a;
                    ex_operand_b <= dmem_rd_data_b;
                end else begin
                    // Bubble into EX (DE stalled or empty)
                    ex_valid <= 1'b0;
                end
            end
            // else: EX holds (ex_stall)

            // --- IF/DE register update ---
            if (de_advance) begin
                if (if_advance && if_valid) begin
                    // IF → DE transfer
                    de_valid   <= 1'b1;
                    de_opcode  <= if_opcode;
                    de_aux     <= if_aux;
                    de_dest    <= if_dest;
                    de_addr_a  <= if_addr_a;
                    de_addr_b  <= if_addr_b;
                    de_pc      <= pc - 16'd1; // PC already incremented
                end else begin
                    // Bubble into DE
                    de_valid <= 1'b0;
                end
            end
            // else: DE holds (de_stall)
        end
    end

    // =========================================================================
    // Scoreboard — DMEM Presence Tracking (v8.0 RDMA-Push)
    // =========================================================================
    // Universal scoreboard: every DMEM write (PIU, GCI, COMPUTE, GENERATE)
    // sets the corresponding bit. DE stalls if reading a 0 bit.
    always_ff @(posedge clk) begin
        if (rst || (pstate == P_IDLE && program_start)) begin
            scoreboard    <= '0;
            scoreboard[0] <= 1'b1;  // DMEM[0] = identity element, always valid
        end else begin
            // PIU write (highest priority — RDMA-Push)
            if (piu_dmem_wr)
                scoreboard[piu_dmem_addr] <= 1'b1;
            // GCI write (accepted — not blocked by PIU)
            if (gci_dmem_wr && !piu_dmem_wr)
                scoreboard[gci_dmem_addr] <= 1'b1;
            // FSM COMPUTE/GENERATE writeback
            if (fsm_dmem_wr && !piu_dmem_wr && !gci_dmem_wr)
                scoreboard[fsm_dmem_addr] <= 1'b1;
        end
    end

    // GCI Pending Tracking (unchanged)
    always_ff @(posedge clk) begin
        if (rst) begin
            gci_pending    <= 1'b0;
            gci_pend_addr  <= 16'd0;
            gci_write_held <= 1'b0;
        end else begin
            // GCI write accepted by arbiter (no PIU contention) — clear pending
            if (gci_pending && (gci_done || gci_write_held) && !piu_dmem_wr) begin
                gci_pending    <= 1'b0;
                gci_write_held <= 1'b0;
            end
            // GCI write blocked by PIU — latch for retry next cycle
            else if (gci_pending && gci_done && piu_dmem_wr) begin
                gci_write_held <= 1'b1;
            end
            // New GENERATE starts GCI
            if (ex_valid && ex_opcode == 4'h1 && ex_advance) begin
                gci_pending    <= 1'b1;
                gci_pend_addr  <= ex_dest;
                gci_write_held <= 1'b0;
            end
        end
    end

    // =========================================================================
    // Pipeline State Machine (top-level control)
    // =========================================================================
    logic pipeline_empty;
    logic all_retired;
    assign pipeline_empty = !de_valid && !ex_valid;
    assign all_retired    = pipeline_empty && !gci_pending;  // No recv_pending in RDMA-Push

    // Error detection
    logic invalid_opcode;
    assign invalid_opcode = ex_valid && ex_advance && (ex_opcode > 4'h3);  // 0x4+ all invalid now

    // Stall timeout counter
    logic [31:0] stall_timer;

    always_ff @(posedge clk) begin
        if (rst) begin
            stall_timer <= 32'd0;
        end else begin
            if (ex_advance || pstate != P_RUN)
                stall_timer <= 32'd0;
            else if (ex_stall)
                stall_timer <= stall_timer + 32'd1;
        end
    end

    // Watchdog: counts cycles without any instruction retiring
    logic [31:0] watchdog;
    logic        any_retired;
    assign any_retired = ex_valid && ex_advance;

    always_ff @(posedge clk) begin
        if (rst) begin
            watchdog <= 32'd0;
        end else if (pstate == P_RUN || pstate == P_DRAIN) begin
            watchdog <= any_retired ? 32'd0 : watchdog + 32'd1;
        end else begin
            watchdog <= 32'd0;
        end
    end

    // State transitions
    always_ff @(posedge clk) begin
        if (rst) begin
            pstate    <= P_IDLE;
            result    <= 64'd0;
            error_pc  <= 16'd0;
            error_state <= 4'd0;
        end else begin
            case (pstate)
                P_IDLE: begin
                    if (program_start)
                        pstate <= P_RUN;
                end

                P_RUN: begin
                    // Capture ALU results for output
                    if (ex_valid && ex_advance && ex_opcode == 4'h2)
                        result <= alu_result_comb;

                    // Transition to DRAIN when IF has no more instructions
                    if (pc_at_end && !if_valid)
                        pstate <= P_DRAIN;

                    // Error checks
                    if (invalid_opcode) begin
                        pstate      <= P_ERROR;
                        error_pc    <= ex_pc;
                        error_state <= 4'd3; // EX stage
                    end
                    if (stall_timer >= TIMEOUT_MAX) begin
                        pstate      <= P_ERROR;
                        error_pc    <= ex_pc;
                        error_state <= 4'd3;
                    end
                    if (watchdog >= WATCHDOG_MAX) begin
                        pstate      <= P_ERROR;
                        error_pc    <= ex_pc;
                        error_state <= 4'd3;
                    end
                end

                P_DRAIN: begin
                    // Capture ALU results
                    if (ex_valid && ex_advance && ex_opcode == 4'h2)
                        result <= alu_result_comb;

                    if (all_retired)
                        pstate <= P_DONE;

                    // Error checks still active during drain
                    if (invalid_opcode) begin
                        pstate      <= P_ERROR;
                        error_pc    <= ex_pc;
                        error_state <= 4'd3;
                    end
                    if (stall_timer >= TIMEOUT_MAX) begin
                        pstate      <= P_ERROR;
                        error_pc    <= ex_pc;
                        error_state <= 4'd3;
                    end
                    if (watchdog >= WATCHDOG_MAX) begin
                        pstate      <= P_ERROR;
                        error_pc    <= ex_pc;
                        error_state <= 4'd3;
                    end
                end

                P_DONE:  ; // Terminal
                P_ERROR: ; // Terminal
                default: pstate <= P_IDLE;
            endcase
        end
    end

    // =========================================================================
    // Output Assignments
    // =========================================================================
    assign done  = (pstate == P_DONE);
    assign error = (pstate == P_ERROR);

    always_comb begin
        case (pstate)
            P_IDLE:  status = 8'h00;
            P_RUN:   status = 8'h01;
            P_DRAIN: status = 8'h02;
            P_DONE:  status = 8'hFF;
            P_ERROR: status = 8'hEE;
            default: status = 8'h00;
        endcase
    end

    // =========================================================================
    // Performance Counters
    // =========================================================================
    logic [31:0] cnt_total, cnt_stall, cnt_retired;

    logic is_active;
    assign is_active = (pstate == P_RUN || pstate == P_DRAIN);

    logic is_stalling;
    assign is_stalling = is_active && (ex_stall || de_hazard);

    always_ff @(posedge clk) begin
        if (rst) begin
            cnt_total   <= 32'd0;
            cnt_stall   <= 32'd0;
            cnt_retired <= 32'd0;
        end else if (is_active) begin
            cnt_total <= cnt_total + 32'd1;
            if (is_stalling)
                cnt_stall <= cnt_stall + 32'd1;
            if (any_retired)
                cnt_retired <= cnt_retired + 32'd1;
        end
    end

    assign perf_total_cycles  = cnt_total;
    assign perf_stall_cycles  = cnt_stall;
    assign perf_instr_retired = cnt_retired;

    // =========================================================================
    // Compatibility: unused IFU output signals
    // (The original btree_fsm exposed these through internal IFU — we replicate
    //  the port interface but IFU is inlined)
    // =========================================================================
    // error_state is already assigned above.
    // error_pc is already assigned above.
    // gci_start, gci_dest_addr already assigned in EX comb block.

endmodule
