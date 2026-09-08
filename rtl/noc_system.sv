// =============================================================================
// noc_system.sv — Topology-Agnostic NoC System (v7.0)
//
// THE core module: instantiates compute nodes, network interfaces, routers,
// and inter-router links — all wired according to an adjacency table
// parameter. Adding a new topology means changing the config, not the RTL.
//
// v7.0 Changes from v6.0:
//   - NUM_VCS parameter passed to routers (default 2)
//   - Inter-router links use noc_link instances with LINK_LATENCY pipeline
//     stages instead of combinational wiring
//   - Structural generate blocks for inter-router wiring
//
// Architecture:
//   compute_node[i] ↔ noc_ni[i] ↔ router[i] port 0 (local)
//   router[i] port p ↔ noc_link ↔ router[j] port q  (from adj_table)
// =============================================================================
`timescale 1ns / 1ps

import noc_pkg::*;

module noc_system #(
    parameter int N_NODES       = 4,      // compute nodes (GPUs)
    parameter int N_ROUTERS     = 4,      // total routers (>= N_NODES for transit switches)
    parameter int PORTS_PER_RTR = 4,      // ports per router (port 0 = local NI for node routers)
    parameter int NUM_VCS       = 2,      // virtual channels per router port
    parameter int RTR_BUF_DEPTH = 8,
    parameter int NI_BUF_DEPTH  = 8,
    parameter int LINK_LATENCY  = 1,
    parameter int CN_NUM_LINKS  = 2,      // btree_fsm_fast NUM_LINKS
    parameter int GCI_BUF_DEPTH = 8,      // leaf values per node
    parameter int CN_TX_BUF     = 8,
    parameter int CN_RX_BUF     = 8,
    parameter int CN_DMEM       = 512,
    parameter int CN_IMEM       = 512,
    parameter int CN_TIMEOUT    = 10000,
    parameter int CN_WATCHDOG   = 20000,
    parameter int GCI_LATENCY   = 4,
    parameter int CN_RT_DEPTH   = 4096,   // routing table depth per router
    parameter int RESULT_NODE   = 0,      // Which GPU reports the root result (CBT Node 0)
    // Width of every field of the adjacency-configuration interface.  The
    // addressable router range is 0 .. 2**ADJ_ID_W - 2, because the all-ones
    // code is the "disconnected" sentinel.  12 (the historical fixed width)
    // therefore tops out at router 4094 and SILENTLY ALIASES anything above it,
    // which is what broke fat_tree G=4096 (4,192 routers).  Widen at the
    // instantiation site for such configurations; 12 keeps every smaller
    // instance bit-identical to the shipped fabric.
    parameter int ADJ_ID_W      = 12
)(
    input  logic        clk,
    input  logic        rst,
    input  logic        program_start,
    output logic        all_done,
    output logic [63:0] result,

    // ── Per-Node State & Error ──
    output logic [N_NODES-1:0][7:0]  status,
    output logic [N_NODES-1:0]       error,
    output logic [N_NODES-1:0][15:0] error_pc,
    output logic [N_NODES-1:0][3:0]  error_state,

    // ── Per-Node IMEM Loading ──
    input  logic [N_NODES-1:0]        imem_wr_en,
    input  logic [N_NODES-1:0][15:0]  imem_wr_addr,
    input  logic [N_NODES-1:0][63:0]  imem_wr_data,
    input  logic [N_NODES-1:0][15:0]  imem_size,

    // ── Router Routing Table Config ──
    input  logic [N_ROUTERS-1:0]                               rtr_rt_wr_en,
    input  logic [N_ROUTERS-1:0][15:0]                         rtr_rt_wr_addr,
    input  logic [N_ROUTERS-1:0][$clog2(PORTS_PER_RTR)-1:0]   rtr_rt_wr_data,

    // ── Adjacency Table Config (loaded before program_start) ──
    input  logic        adj_wr_en,
    input  logic [ADJ_ID_W-1:0] adj_rtr_id,
    input  logic [ADJ_ID_W-1:0] adj_port_id,
    input  logic [ADJ_ID_W-1:0] adj_target_rtr,
    input  logic [ADJ_ID_W-1:0] adj_target_port,

    // ── GCI Buffer Load (leaf values, loaded at runtime) ──
    input  logic [N_NODES-1:0]        gci_buf_wr_en,
    input  logic [N_NODES-1:0][15:0]  gci_buf_wr_addr,
    input  logic [N_NODES-1:0][63:0]  gci_buf_wr_data,

    // ── Per-Node Performance Counters ──
    output logic [N_NODES-1:0][31:0]  perf_total,
    output logic [N_NODES-1:0][31:0]  perf_stall,
    output logic [N_NODES-1:0][31:0]  perf_retired
);

    // =========================================================================
    // Adjacency Table Storage
    // adj_table[router][port] = {target_router, target_port}, ADJ_ID_W bits each
    // All-ones ({ADJ_ID_W{1'b1}}) for target_router means disconnected
    // =========================================================================
    localparam logic [ADJ_ID_W-1:0] ADJ_DISC_CODE = {ADJ_ID_W{1'b1}};
    logic [ADJ_ID_W-1:0] adj_tgt_rtr  [0:N_ROUTERS-1][0:PORTS_PER_RTR-1];
    logic [ADJ_ID_W-1:0] adj_tgt_port [0:N_ROUTERS-1][0:PORTS_PER_RTR-1];

    // The sentinel steals one code point, so the last addressable router is
    // 2**ADJ_ID_W - 2.  Fail loudly at elaboration instead of aliasing silently.
    generate
        if (N_ROUTERS > (2**ADJ_ID_W) - 1) begin : gen_adj_width_check
            initial $fatal(1,
                "noc_system: N_ROUTERS=%0d exceeds the ADJ_ID_W=%0d adjacency range (max addressable %0d); widen ADJ_ID_W",
                N_ROUTERS, ADJ_ID_W, (2**ADJ_ID_W) - 2);
        end
    endgenerate

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int r = 0; r < N_ROUTERS; r++)
                for (int p = 0; p < PORTS_PER_RTR; p++) begin
                    adj_tgt_rtr[r][p]  <= ADJ_DISC_CODE;  // disconnected
                    adj_tgt_port[r][p] <= ADJ_DISC_CODE;
                end
        end else if (adj_wr_en) begin
            $display("[NOC_SYS] WRITE ADJ: [%0d][%0d] <- TGT_RTR:%0d TGT_PRT:%0d", adj_rtr_id, adj_port_id, adj_target_rtr, adj_target_port);
            adj_tgt_rtr[adj_rtr_id][adj_port_id]  <= adj_target_rtr;
            adj_tgt_port[adj_rtr_id][adj_port_id] <= adj_target_port;
        end
    end

    // =========================================================================
    // Router Port Signals
    // =========================================================================
    logic [N_ROUTERS-1:0][PORTS_PER_RTR-1:0]        rtr_rx_valid;
    logic [N_ROUTERS-1:0][PORTS_PER_RTR-1:0][95:0]  rtr_rx_data;
    logic [N_ROUTERS-1:0][PORTS_PER_RTR-1:0]        rtr_credit_out;
    logic [N_ROUTERS-1:0][PORTS_PER_RTR-1:0]        rtr_tx_valid;
    logic [N_ROUTERS-1:0][PORTS_PER_RTR-1:0][95:0]  rtr_tx_data;
    logic [N_ROUTERS-1:0][PORTS_PER_RTR-1:0]        rtr_credit_in;

    // =========================================================================
    // Compute Nodes + Network Interfaces (for nodes 0..N_NODES-1)
    // Each node's NI connects to router[node_id] port 0
    // =========================================================================
    logic [N_NODES-1:0]        cn_done;
    logic [N_NODES-1:0][63:0]  cn_result;

    // CN ↔ NI link signals
    logic [N_NODES-1:0][CN_NUM_LINKS-1:0]        cn_tx_valid;
    logic [N_NODES-1:0][CN_NUM_LINKS-1:0][95:0]  cn_tx_data;
    logic [N_NODES-1:0][CN_NUM_LINKS-1:0]        cn_credit_in;
    logic [N_NODES-1:0][CN_NUM_LINKS-1:0]        cn_rx_valid;
    logic [N_NODES-1:0][CN_NUM_LINKS-1:0][95:0]  cn_rx_data;
    logic [N_NODES-1:0][CN_NUM_LINKS-1:0]        cn_credit_out;

    // GCI signals
    logic [N_NODES-1:0]        cn_gci_start;
    logic [N_NODES-1:0][15:0]  cn_gci_dest;
    logic [N_NODES-1:0]        cn_gci_done;
    logic [N_NODES-1:0][63:0]  cn_gci_result;

    // NI ↔ Router port 0 signals
    logic [N_NODES-1:0]        ni_tx_valid;
    logic [N_NODES-1:0][95:0]  ni_tx_data;
    logic [N_NODES-1:0]        ni_credit_in;
    logic [N_NODES-1:0]        ni_rx_valid;
    logic [N_NODES-1:0][95:0]  ni_rx_data;
    logic [N_NODES-1:0]        ni_credit_out;

    genvar gi;
    generate
        for (gi = 0; gi < N_NODES; gi++) begin : gen_node
            // ── Compute Node ──
            btree_fsm_fast #(
                .NUM_LINKS   (CN_NUM_LINKS),
                .TX_BUF_DEPTH(RTR_BUF_DEPTH), // Intercepted to align with router flow-control
                .RX_BUF_DEPTH(RTR_BUF_DEPTH), // Intercepted to align with router flow-control
                .DMEM_DEPTH  (CN_DMEM),
                .IMEM_DEPTH  (CN_IMEM),
                .TIMEOUT_MAX (CN_TIMEOUT),
                .WATCHDOG_MAX(CN_WATCHDOG)
            ) u_cn (
                .clk(clk), .rst(rst),
                .gpu_id          (gi[15:0]),
                .program_start   (program_start),
                .done            (cn_done[gi]),
                .status          (status[gi]),
                .result          (cn_result[gi]),
                .error           (error[gi]),
                .imem_wr_en      (imem_wr_en[gi]),
                .imem_wr_addr    (imem_wr_addr[gi]),
                .imem_wr_data    (imem_wr_data[gi]),
                .imem_size       (imem_size[gi]),
                .gci_start       (cn_gci_start[gi]),
                .gci_dest_addr   (cn_gci_dest[gi]),
                .gci_done        (cn_gci_done[gi]),
                .gci_result      (cn_gci_result[gi]),
                .error_pc        (error_pc[gi]),
                .error_state     (error_state[gi]),
                .perf_total_cycles  (perf_total[gi]),
                .perf_stall_cycles  (perf_stall[gi]),
                .perf_instr_retired (perf_retired[gi]),
                .link_rx_valid   (cn_rx_valid[gi]),
                .link_rx_data    (cn_rx_data[gi]),
                .link_tx_valid   (cn_tx_valid[gi]),
                .link_tx_data    (cn_tx_data[gi]),
                .link_credit_in  (cn_credit_in[gi]),
                .link_credit_out (cn_credit_out[gi]),
                .rt_wr_en        (1'b0),    // CN routing table unused in v6+
                .rt_wr_addr      (12'd0),
                .rt_wr_data      ('0)
            );

            // ── Network Interface ──
            noc_ni #(
                .NODE_ID      (gi),
                .NUM_LINKS    (CN_NUM_LINKS),
                .GCI_LATENCY  (GCI_LATENCY),
                .GCI_BUF_DEPTH(GCI_BUF_DEPTH),
                .BUF_DEPTH    (NI_BUF_DEPTH)
            ) u_ni (
                .clk(clk), .rst(rst),
                .cn_tx_valid  (cn_tx_valid[gi]),
                .cn_tx_data   (cn_tx_data[gi]),
                .cn_credit_in (cn_credit_in[gi]),
                .cn_rx_valid  (cn_rx_valid[gi]),
                .cn_rx_data   (cn_rx_data[gi]),
                .cn_credit_out(cn_credit_out[gi]),
                .gci_start    (cn_gci_start[gi]),
                .gci_dest_addr(cn_gci_dest[gi]),
                .gci_done     (cn_gci_done[gi]),
                .gci_result   (cn_gci_result[gi]),
                .gci_buf_wr_en  (gci_buf_wr_en[gi]),
                .gci_buf_wr_addr(gci_buf_wr_addr[gi]),
                .gci_buf_wr_data(gci_buf_wr_data[gi]),
                .rtr_tx_valid (ni_tx_valid[gi]),
                .rtr_tx_data  (ni_tx_data[gi]),
                .rtr_credit_in(ni_credit_in[gi]),
                .rtr_rx_valid (ni_rx_valid[gi]),
                .rtr_rx_data  (ni_rx_data[gi]),
                .rtr_credit_out(ni_credit_out[gi])
            );

            // ── Wire Router Output to NI ──
            // (Router inputs are mapped in the always_comb below to prevent multi-drivers)
            assign ni_credit_in[gi]     = rtr_credit_out[gi][0];
            assign ni_rx_valid[gi]      = rtr_tx_valid[gi][0];
            assign ni_rx_data[gi]       = rtr_tx_data[gi][0];
        end
    endgenerate

    // =========================================================================
    // Routers (v7.0: with NUM_VCS parameter)
    // =========================================================================
    generate
        for (gi = 0; gi < N_ROUTERS; gi++) begin : gen_rtr
            noc_router #(
                .ROUTER_ID       (gi),
                .NUM_PORTS       (PORTS_PER_RTR),
                .NUM_VCS         (NUM_VCS),
                .BUF_DEPTH       (RTR_BUF_DEPTH),
                .ROUTE_TABLE_DEPTH(CN_RT_DEPTH)
            ) u_rtr (
                .clk(clk), .rst(rst),
                .rt_wr_en  (rtr_rt_wr_en[gi]),
                .rt_wr_addr(rtr_rt_wr_addr[gi]),
                .rt_wr_data(rtr_rt_wr_data[gi]),
                .rx_valid  (rtr_rx_valid[gi]),
                .rx_data   (rtr_rx_data[gi]),
                .credit_out(rtr_credit_out[gi]),
                .tx_valid  (rtr_tx_valid[gi]),
                .tx_data   (rtr_tx_data[gi]),
                .credit_in (rtr_credit_in[gi])
            );
        end
    endgenerate

    // =========================================================================
    // Adjacency-Driven Inter-Router Wiring via noc_link Instances
    //
    // For each router R, port P (skipping port 0 which is the local NI):
    //   If adj_tgt_rtr[R][P] != ADJ_DISC_CODE, populate routing paths dynamically
    // =========================================================================
    always_comb begin
        // Default: all ports disconnected
        for (int r = 0; r < N_ROUTERS; r++) begin
            for (int p = 0; p < PORTS_PER_RTR; p++) begin
                rtr_rx_valid[r][p]  = 1'b0;
                rtr_rx_data[r][p]   = 96'd0;
                rtr_credit_in[r][p] = 1'b0;
            end
        end

        // Priority 1: Connect local NIs explicitly (unconditional, overwrites default)
        for (int r = 0; r < N_NODES; r++) begin
            rtr_rx_valid[r][0]  = ni_tx_valid[r];
            rtr_rx_data[r][0]   = ni_tx_data[r];
            rtr_credit_in[r][0] = ni_credit_out[r];
        end

        // Wire based on adjacency table
        for (int r = 0; r < N_ROUTERS; r++) begin
            for (int p = 0; p < PORTS_PER_RTR; p++) begin
                if (adj_tgt_rtr[r][p] != ADJ_DISC_CODE) begin
                    automatic int tr = adj_tgt_rtr[r][p];
                    automatic int tp = adj_tgt_port[r][p];
                    if (tr < N_ROUTERS && tp < PORTS_PER_RTR) begin
                        // Forward path: R.tx[P] → tgt.rx[tp]
                        if (tp != 0 || tr >= N_NODES) begin
                           rtr_rx_valid[tr][tp]  = rtr_tx_valid[r][p];
                           rtr_rx_data[tr][tp]   = rtr_tx_data[r][p];
                        end
                        // Reverse path: tgt.credit_out[tp] → R.credit_in[P]
                        if (p != 0 || r >= N_NODES) begin
                           rtr_credit_in[r][p]   = rtr_credit_out[tr][tp];
                        end
                    end
                end
            end
        end
    end

    // =========================================================================
    // Outputs
    // =========================================================================
    assign all_done = &cn_done;
    assign result   = cn_result[RESULT_NODE];

endmodule
