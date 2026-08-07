// =============================================================================
// noc_router.sv — N-Port, Multi-VC NoC Router (v7.0)
//
// Enhanced from v6.0 with Virtual Channel (VC) support for deadlock freedom.
//
// Pipeline (same 3-stage structure, VC-aware):
//   Stage 1: Input Buffering (per-port, per-VC FIFOs)
//   Stage 2: Route Computation (table lookup) + VC/Switch Allocation (RR)
//   Stage 3: Switch Traversal (crossbar transfer to egress)
//
// Virtual Channel Design:
//   - NUM_VCS input FIFOs per port (default 2)
//   - VC assignment: packet bit [63] selects VC (software-controlled)
//     This allows the compiler to assign VCs for deadlock-free routing.
//   - Arbitration: two-level — per-VC round-robin, then per-output-port RR
//   - Output: single egress FIFO per port (VCs only on input side)
//   - Credit tracking: per-port (shared across VCs at egress)
//
// Key benefit: eliminates head-of-line (HOL) blocking and enables
// deadlock-free routing in cyclic topologies (mesh, torus) when VCs are
// assigned correctly by the software layer.
// =============================================================================
`timescale 1ns / 1ps

import noc_pkg::*;

module noc_router #(
    parameter int ROUTER_ID         = 0,
    parameter int NUM_PORTS         = 4,
    parameter int NUM_VCS           = 2,     // virtual channels per port
    parameter int BUF_DEPTH         = 8,
    parameter int ROUTE_TABLE_DEPTH = 4096
)(
    input  logic        clk,
    input  logic        rst,

    // ── Routing Table Config ──
    input  logic        rt_wr_en,
    input  logic [15:0] rt_wr_addr,
    input  logic [$clog2(NUM_PORTS)-1:0] rt_wr_data,

    // ── Per-Port Link Interfaces ──
    input  logic [NUM_PORTS-1:0]        rx_valid,
    input  logic [NUM_PORTS-1:0][95:0]  rx_data,
    output logic [NUM_PORTS-1:0]        credit_out,

    output logic [NUM_PORTS-1:0]        tx_valid,
    output logic [NUM_PORTS-1:0][95:0]  tx_data,
    input  logic [NUM_PORTS-1:0]        credit_in
);

    localparam int PORT_W = $clog2(NUM_PORTS) > 0 ? $clog2(NUM_PORTS) : 1;
    localparam int RT_AW  = $clog2(ROUTE_TABLE_DEPTH);
    localparam int VC_W   = $clog2(NUM_VCS) > 0 ? $clog2(NUM_VCS) : 1;

    // =========================================================================
    // Routing Table (SRAM) — no reset, config-only
    // =========================================================================
    logic [PORT_W-1:0] route_table [0:ROUTE_TABLE_DEPTH-1];

    always_ff @(posedge clk) begin
        if (rt_wr_en)
            route_table[rt_wr_addr[RT_AW-1:0]] <= rt_wr_data;
    end

    initial begin
        for (int i = 0; i < ROUTE_TABLE_DEPTH; i++)
            route_table[i] = '0;
    end

    // =========================================================================
    // Stage 1: Input Buffers — per-port, per-VC FIFOs
    //
    // Each port has NUM_VCS FIFOs. Incoming packets are steered to a VC
    // based on packet bit [63] (allows software VC assignment).
    // =========================================================================
    logic [95:0]  ibuf_rdata  [0:NUM_PORTS-1][0:NUM_VCS-1];
    logic         ibuf_rrdy   [0:NUM_PORTS-1][0:NUM_VCS-1];
    logic         ibuf_ren    [0:NUM_PORTS-1][0:NUM_VCS-1];
    logic         ibuf_wrdy   [0:NUM_PORTS-1][0:NUM_VCS-1];
    logic         ibuf_wen    [0:NUM_PORTS-1][0:NUM_VCS-1];
    logic [95:0]  ibuf_wdata  [0:NUM_PORTS-1][0:NUM_VCS-1];

    genvar gp, gv;
    generate
        for (gp = 0; gp < NUM_PORTS; gp++) begin : gen_port
            for (gv = 0; gv < NUM_VCS; gv++) begin : gen_vc
                sync_fifo #(.WIDTH(96), .DEPTH(BUF_DEPTH)) u_ibuf (
                    .clk(clk), .rst(rst),
                    .w_data(ibuf_wdata[gp][gv]),
                    .w_en(ibuf_wen[gp][gv]),
                    .w_rdy(ibuf_wrdy[gp][gv]),
                    .r_data(ibuf_rdata[gp][gv]),
                    .r_en(ibuf_ren[gp][gv]),
                    .r_rdy(ibuf_rrdy[gp][gv]),
                    .level()
                );
            end
        end
    endgenerate

    // VC steering: direct incoming packets to correct VC FIFO
    // VC selection uses bit [63] of payload (software-configurable)
    always_comb begin
        for (int p = 0; p < NUM_PORTS; p++) begin
            for (int v = 0; v < NUM_VCS; v++) begin
                ibuf_wdata[p][v] = rx_data[p];
                if (NUM_VCS == 1) begin
                    ibuf_wen[p][v] = rx_valid[p] && ibuf_wrdy[p][v];
                end else begin
                    // Use bit [64] for VC 0/1 selection (2 VCs)
                    // For >2 VCs, use bits [64 -: VC_W]
                    if (v[VC_W-1:0] == rx_data[p][64 -: VC_W])
                        ibuf_wen[p][v] = rx_valid[p] && ibuf_wrdy[p][v];
                    else
                        ibuf_wen[p][v] = 1'b0;
                end
            end
        end
    end

    // Per-packet tracing. Unconditional tracing costs hours of wall-clock on
    // large configurations (4096 routers x every packet), so it is opt-in:
    // compile with -d NOC_TRACE to enable. $display cannot affect signal
    // values or consume simulation time, so gating it does not change results.
`ifdef NOC_TRACE
    always_ff @(posedge clk) begin
        for (int jp = 0; jp < NUM_PORTS; jp++) begin
            if (rx_valid[jp])
                $display("[NOCTRC] %0t | Router %0d RX Port %0d: pkt=%0h (tgt=%0d, src=%0d)", $time, ROUTER_ID, jp, rx_data[jp], rx_data[jp][95:80], rx_data[jp][79:64]);
            if (tx_valid[jp])
                $display("[NOCTRC] %0t | Router %0d TX Port %0d: pkt=%0h (tgt=%0d, src=%0d)", $time, ROUTER_ID, jp, tx_data[jp], tx_data[jp][95:80], tx_data[jp][79:64]);
        end
    end
`endif

    // =========================================================================
    // Stage 3: Output — per-port egress FIFOs + credit TX controllers
    // (single FIFO per port, shared across VCs — VCs are input-side only)
    // =========================================================================
    logic [95:0]  obuf_wdata  [0:NUM_PORTS-1];
    logic         obuf_wen    [0:NUM_PORTS-1];
    logic         obuf_wrdy   [0:NUM_PORTS-1];
    logic [95:0]  obuf_rdata  [0:NUM_PORTS-1];
    logic         obuf_rrdy   [0:NUM_PORTS-1];
    logic         obuf_ren    [0:NUM_PORTS-1];
    logic         txc_rdy     [0:NUM_PORTS-1];

    generate
        for (gp = 0; gp < NUM_PORTS; gp++) begin : gen_obuf
            sync_fifo #(.WIDTH(96), .DEPTH(BUF_DEPTH)) u_obuf (
                .clk(clk), .rst(rst),
                .w_data(obuf_wdata[gp]),
                .w_en(obuf_wen[gp]),
                .w_rdy(obuf_wrdy[gp]),
                .r_data(obuf_rdata[gp]),
                .r_en(obuf_ren[gp]),
                .r_rdy(obuf_rrdy[gp]),
                .level()
            );

            link_tx #(.RX_BUF_DEPTH(BUF_DEPTH)) u_txc (
                .clk(clk), .rst(rst),
                .send_en(obuf_rrdy[gp]),
                .send_data(obuf_rdata[gp]),
                .send_rdy(txc_rdy[gp]),
                .tx_valid(tx_valid[gp]),
                .tx_data(tx_data[gp]),
                .credit_return(credit_in[gp])
            );

            assign obuf_ren[gp] = obuf_rrdy[gp] && txc_rdy[gp];
        end
    endgenerate

    // =========================================================================
    // Credit Return
    // Pulse when any VC buffer on a port consumes a flit.
    // =========================================================================
    // Credit return: count how many VC FIFOs were read per port per cycle.
    // BUG FIX: old code used a single-bit pulse that collapsed multiple VC
    // reads into one credit return, causing a credit leak / eventual deadlock.
    // New code: use a counter to pulse once per VC read. Since the upstream
    // link_tx expects a single-bit pulse per credit, we serialize multi-read
    // events across cycles using a pending-credit counter.
    logic [NUM_PORTS-1:0] credit_pulse;
    logic [NUM_PORTS-1:0][$clog2(NUM_VCS+1)-1:0] credit_pending;

    always_ff @(posedge clk) begin
        if (rst) begin
            credit_pulse   <= '0;
            for (int p = 0; p < NUM_PORTS; p++)
                credit_pending[p] <= '0;
        end else begin
            for (int p = 0; p < NUM_PORTS; p++) begin
                // Count new VC reads this cycle
                logic [$clog2(NUM_VCS+1)-1:0] new_reads;
                new_reads = '0;
                for (int v = 0; v < NUM_VCS; v++)
                    if (ibuf_ren[p][v]) new_reads = new_reads + 1;

                // Add new reads, subtract 1 if we're sending a pulse
                if (credit_pending[p] > 0 || new_reads > 0) begin
                    credit_pulse[p]   <= 1'b1;
                    credit_pending[p] <= credit_pending[p] + new_reads - 1;
                end else begin
                    credit_pulse[p]   <= 1'b0;
                end
            end
        end
    end

    assign credit_out = credit_pulse;

    // =========================================================================
    // Stage 2: Route Computation + VC-Aware Switch Allocation
    //
    // For each (input_port, vc) pair with a ready packet:
    //   1. Look up dest_id in routing table → target output port
    //   2. Two-level arbitration:
    //      a. Per-output-port: round-robin across all (port, vc) candidates
    //   Only one winner per output port per cycle.
    // =========================================================================

    // Route lookup: for each (port, vc) pair
    logic [PORT_W-1:0] inp_target [0:NUM_PORTS-1][0:NUM_VCS-1];
    logic              inp_valid  [0:NUM_PORTS-1][0:NUM_VCS-1];

    always_comb begin
        for (int p = 0; p < NUM_PORTS; p++) begin
            for (int v = 0; v < NUM_VCS; v++) begin
                inp_target[p][v] = route_table[ibuf_rdata[p][v][95:80] & (ROUTE_TABLE_DEPTH-1)];
                inp_valid[p][v]  = ibuf_rrdy[p][v];
            end
        end
    end

    // Flattened candidate count for round-robin
    localparam int NUM_CANDIDATES = NUM_PORTS * NUM_VCS;
    localparam int CAND_W = $clog2(NUM_CANDIDATES) > 0 ? $clog2(NUM_CANDIDATES) : 1;

    // Round-robin priority (per output port)
    logic [CAND_W-1:0] rr_ptr [0:NUM_PORTS-1];

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < NUM_PORTS; i++)
                rr_ptr[i] <= '0;
        end else begin
            for (int i = 0; i < NUM_PORTS; i++)
                if (obuf_wen[i])
                    rr_ptr[i] <= (rr_ptr[i] + 1) % NUM_CANDIDATES;
        end
    end

    // Crossbar arbitration (combinational)
    always_comb begin
        // Track which (port, vc) inputs have been consumed
        logic [NUM_PORTS-1:0][NUM_VCS-1:0] v_ibuf_ren;
        logic [NUM_PORTS-1:0]              v_obuf_wen;
        logic [95:0]                       v_obuf_wdata [NUM_PORTS];

        v_ibuf_ren = '0;
        v_obuf_wen = '0;
        for (int i = 0; i < NUM_PORTS; i++)
            v_obuf_wdata[i] = 96'd0;

        // For each output port, find the winning (port, vc) candidate
        for (int oport = 0; oport < NUM_PORTS; oport++) begin
            for (int off = 0; off < NUM_CANDIDATES; off++) begin
                // Flatten: candidate index → (port, vc)
                int cand_idx;
                int cand_port;
                int cand_vc;
                cand_idx  = (rr_ptr[oport] + off) % NUM_CANDIDATES;
                cand_port = cand_idx / NUM_VCS;
                cand_vc   = cand_idx % NUM_VCS;

                if (inp_valid[cand_port][cand_vc] &&
                    inp_target[cand_port][cand_vc] == oport[PORT_W-1:0] &&
                    obuf_wrdy[oport] &&
                    !v_obuf_wen[oport] &&
                    !v_ibuf_ren[cand_port][cand_vc])
                begin
                    v_obuf_wen[oport]                = 1'b1;
                    v_obuf_wdata[oport]              = ibuf_rdata[cand_port][cand_vc];
                    v_ibuf_ren[cand_port][cand_vc]   = 1'b1;
                end
            end
        end

        // Drive outputs
        for (int p = 0; p < NUM_PORTS; p++) begin
            obuf_wen[p]   = v_obuf_wen[p];
            obuf_wdata[p] = v_obuf_wdata[p];
            for (int v = 0; v < NUM_VCS; v++)
                ibuf_ren[p][v] = v_ibuf_ren[p][v];
        end
    end

endmodule
