// =============================================================================
// link_tx.sv — Per-Link TX with Credit-Based Flow Control (v4.1)
// 96-bit packets. Credit-only. No ARQ.
// =============================================================================
module link_tx #(
    parameter int RX_BUF_DEPTH = 8
)(
    input  logic        clk,
    input  logic        rst,
    // Send interface
    input  logic        send_en,
    input  logic [95:0] send_data,     // 96-bit packet
    output logic        send_rdy,
    // TX output (to link)
    output logic        tx_valid,
    output logic [95:0] tx_data,
    // Credit flow control
    input  logic        credit_return
);

    logic [7:0] credits;

    assign send_rdy = (credits > 0);
    assign tx_valid = send_en && send_rdy;
    assign tx_data  = send_data;

    always_ff @(posedge clk) begin
        if (rst) begin
            credits <= RX_BUF_DEPTH[7:0];
        end else begin
            credits <= credits
                       + {7'd0, credit_return}
                       - {7'd0, (send_en && send_rdy)};
        end
    end

endmodule
