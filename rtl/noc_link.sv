// =============================================================================
// noc_link.sv — Configurable-Latency Inter-Router Link (v6.0)
//
// Models wire delay between routers as a pipeline register chain.
// LATENCY=0: combinational passthrough (zero-cycle)
// LATENCY=1: single pipeline register
// LATENCY=N: N-stage shift register
//
// Handles both forward data path and reverse credit path.
// =============================================================================
`timescale 1ns / 1ps

module noc_link #(
    parameter int LATENCY = 1   // pipeline stages (0 = wire)
)(
    input  logic        clk,
    input  logic        rst,

    // ── Source side (from TX of source router) ──
    input  logic        src_valid,
    input  logic [95:0] src_data,
    output logic        src_credit,

    // ── Dest side (to RX of dest router) ──
    output logic        dst_valid,
    output logic [95:0] dst_data,
    input  logic        dst_credit
);

    generate
        if (LATENCY == 0) begin : gen_wire
            // Combinational passthrough
            assign dst_valid  = src_valid;
            assign dst_data   = src_data;
            assign src_credit = dst_credit;
        end else begin : gen_pipe
            // Forward path pipeline
            logic        fwd_valid [0:LATENCY-1];
            logic [95:0] fwd_data  [0:LATENCY-1];

            always_ff @(posedge clk) begin
                if (rst) begin
                    for (int i = 0; i < LATENCY; i++) begin
                        fwd_valid[i] <= 1'b0;
                        fwd_data[i]  <= 96'd0;
                    end
                end else begin
                    fwd_valid[0] <= src_valid;
                    fwd_data[0]  <= src_data;
                    for (int i = 1; i < LATENCY; i++) begin
                        fwd_valid[i] <= fwd_valid[i-1];
                        fwd_data[i]  <= fwd_data[i-1];
                    end
                end
            end

            assign dst_valid = fwd_valid[LATENCY-1];
            assign dst_data  = fwd_data[LATENCY-1];

            // Reverse credit path pipeline
            logic rev_credit [0:LATENCY-1];

            always_ff @(posedge clk) begin
                if (rst) begin
                    for (int i = 0; i < LATENCY; i++)
                        rev_credit[i] <= 1'b0;
                end else begin
                    rev_credit[0] <= dst_credit;
                    for (int i = 1; i < LATENCY; i++)
                        rev_credit[i] <= rev_credit[i-1];
                end
            end

            assign src_credit = rev_credit[LATENCY-1];
        end
    endgenerate

endmodule
