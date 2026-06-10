// =============================================================================
// noc_ni.sv — Network Interface: Compute Node ↔ Router Bridge (v7.0)
//
// Adapts the btree_fsm_fast multi-link interface to a single router port.
//
// Functions:
//   - Injection: Merges all of the FSM's TX links into a single stream
//     sent to the router's local port
//   - Ejection: Receives packets from the router, delivers to the FSM's
//     RX FIFOs (broadcasts to link 0 since PIU handles delivery)
//   - GCI Buffer: Loadable buffer that feeds leaf values to GENERATE
//     instructions, simulating data arriving from a real GPU
//
// v7.0 Changes:
//   - GCI stub replaced with a loadable buffer (gci_buf_wr_en/addr/data)
//   - GENERATE reads the next value from the buffer sequentially
//   - Buffer is loaded at runtime (via VIO or config FSM)
// =============================================================================
`timescale 1ns / 1ps

import noc_pkg::*;

module noc_ni #(
    parameter int NODE_ID       = 0,
    parameter int NUM_LINKS     = 2,    // must match btree_fsm_fast NUM_LINKS
    parameter int GCI_LATENCY   = 4,
    parameter int GCI_BUF_DEPTH = 8,    // max leaf values per node
    parameter int BUF_DEPTH     = 8
)(
    input  logic        clk,
    input  logic        rst,

    // ── Compute Node side (btree_fsm_fast link ports) ──
    // TX from compute node (FSM wants to send packets)
    input  logic [NUM_LINKS-1:0]        cn_tx_valid,
    input  logic [NUM_LINKS-1:0][95:0]  cn_tx_data,
    output logic [NUM_LINKS-1:0]        cn_credit_in,

    // RX to compute node (packets arriving for this node)
    output logic [NUM_LINKS-1:0]        cn_rx_valid,
    output logic [NUM_LINKS-1:0][95:0]  cn_rx_data,
    input  logic [NUM_LINKS-1:0]        cn_credit_out,

    // ── GCI Interface (from compute node) ──
    input  logic        gci_start,
    input  logic [15:0] gci_dest_addr,
    output logic        gci_done,
    output logic [63:0] gci_result,

    // ── GCI Buffer Load Interface (from top-level / VIO) ──
    input  logic        gci_buf_wr_en,
    input  logic [15:0] gci_buf_wr_addr,
    input  logic [63:0] gci_buf_wr_data,

    // ── Router side (single port) ──
    // TX to router (injection)
    output logic        rtr_tx_valid,
    output logic [95:0] rtr_tx_data,
    input  logic        rtr_credit_in,

    // RX from router (ejection)
    input  logic        rtr_rx_valid,
    input  logic [95:0] rtr_rx_data,
    output logic        rtr_credit_out
);

    localparam int LINK_W = $clog2(NUM_LINKS) > 0 ? $clog2(NUM_LINKS) : 1;

    // =========================================================================
    // Injection: Merge CN TX links → single router TX
    //
    // Round-robin across the FSM's TX links. When a link has valid data,
    // forward it to the router port (if credit available).
    // =========================================================================
    logic [LINK_W-1:0] inj_rr;
    logic              inj_granted;
    logic [LINK_W-1:0] inj_winner;

    // Round-robin selection
    always_comb begin
        inj_granted = 1'b0;
        inj_winner  = '0;
        for (int off = 0; off < NUM_LINKS; off++) begin
            automatic int idx = (inj_rr + off) % NUM_LINKS;
            if (!inj_granted && cn_tx_valid[idx]) begin
                inj_granted = 1'b1;
                inj_winner  = idx[LINK_W-1:0];
            end
        end
    end

    // Injection FIFO (buffers packets before sending to router)
    logic [95:0] inj_fifo_wdata;
    logic        inj_fifo_wen, inj_fifo_wrdy;
    logic [95:0] inj_fifo_rdata;
    logic        inj_fifo_ren, inj_fifo_rrdy;

    sync_fifo #(.WIDTH(96), .DEPTH(BUF_DEPTH)) u_inj_fifo (
        .clk(clk), .rst(rst),
        .w_data(inj_fifo_wdata), .w_en(inj_fifo_wen), .w_rdy(inj_fifo_wrdy),
        .r_data(inj_fifo_rdata), .r_en(inj_fifo_ren), .r_rdy(inj_fifo_rrdy),
        .level()
    );

    assign inj_fifo_wdata = cn_tx_data[inj_winner];
    assign inj_fifo_wen   = inj_granted && inj_fifo_wrdy;

    // Credit return to CN TX links (consumed into injection FIFO)
    always_comb begin
        automatic logic [NUM_LINKS-1:0] v_cn_credit_in = '0;
        if (inj_fifo_wen)
            v_cn_credit_in[inj_winner] = 1'b1;
        
        for (int i = 0; i < NUM_LINKS; i++) begin
            cn_credit_in[i] = v_cn_credit_in[i];
        end
    end

    // Update round-robin pointer
    always_ff @(posedge clk) begin
        if (rst)
            inj_rr <= '0;
        else if (inj_fifo_wen)
            inj_rr <= inj_rr + 1;
    end

    // Injection FIFO → Router TX (with credit-based link_tx)
    logic txc_rdy;

    link_tx #(.RX_BUF_DEPTH(BUF_DEPTH)) u_inj_txc (
        .clk(clk), .rst(rst),
        .send_en(inj_fifo_rrdy),
        .send_data(inj_fifo_rdata),
        .send_rdy(txc_rdy),
        .tx_valid(rtr_tx_valid),
        .tx_data(rtr_tx_data),
        .credit_return(rtr_credit_in)
    );

    assign inj_fifo_ren = inj_fifo_rrdy && txc_rdy;

    // =========================================================================
    // Ejection: Router RX → CN RX link 0
    //
    // All incoming packets are delivered to the compute node's link 0 RX.
    // The FSM's PIU will handle them (deliver to DMEM).
    // =========================================================================
    always_comb begin
        for (int i = 0; i < NUM_LINKS; i++) begin
            cn_rx_valid[i] = 1'b0;
            cn_rx_data[i]  = 96'd0;
        end
        cn_rx_valid[0] = rtr_rx_valid;
        cn_rx_data[0]  = rtr_rx_data;
    end

    // Credit back to router = CN's credit out on link 0
    assign rtr_credit_out = cn_credit_out[0];

    // =========================================================================
    // GCI Buffer: Loadable Leaf Value Source
    //
    // Replaces the trivial GCI stub. Each GENERATE instruction reads the
    // next value from gci_buffer[gci_rd_ptr] and increments the pointer.
    // Buffer is loaded via gci_buf_wr_en/addr/data before program_start.
    //
    // Flow: VIO or config FSM writes leaf values → program starts →
    //       GENERATE reads gci_buffer[0], gci_buffer[1], ... sequentially
    // =========================================================================
    localparam int GCI_AW = $clog2(GCI_BUF_DEPTH) > 0 ? $clog2(GCI_BUF_DEPTH) : 1;

    logic [63:0]     gci_buffer [0:GCI_BUF_DEPTH-1];
    logic [GCI_AW:0] gci_rd_ptr;  // one extra bit for overflow detection
    logic [3:0]      gci_ctr;
    logic            gci_run;
    logic [15:0]     gci_addr;

    // Buffer write (from VIO or config FSM)
    always_ff @(posedge clk) begin
        if (gci_buf_wr_en)
            gci_buffer[gci_buf_wr_addr[GCI_AW-1:0]] <= gci_buf_wr_data;
    end

    // FPGA initial values
    initial begin
        for (int i = 0; i < GCI_BUF_DEPTH; i++)
            gci_buffer[i] = 64'd0;
    end

    // GCI state machine: on GENERATE, wait GCI_LATENCY cycles then return buffer[rd_ptr++]
    always_ff @(posedge clk) begin
        if (rst) begin
            gci_run    <= 1'b0;
            gci_ctr    <= 4'd0;
            gci_addr   <= 16'd0;
            gci_done   <= 1'b0;
            gci_result <= 64'd0;
            gci_rd_ptr <= '0;
        end else begin
            gci_done <= 1'b0;
            if (gci_start && !gci_run) begin
                gci_run  <= 1'b1;
                gci_ctr  <= 4'd0;
                gci_addr <= gci_dest_addr;
            end else if (gci_run) begin
                gci_ctr <= gci_ctr + 4'd1;
                if (gci_ctr >= GCI_LATENCY - 1) begin
                    gci_run    <= 1'b0;
                    gci_done   <= 1'b1;
                    gci_result <= gci_buffer[gci_rd_ptr[GCI_AW-1:0]];
                    gci_rd_ptr <= gci_rd_ptr + 1;
                end
            end
        end
    end

endmodule
