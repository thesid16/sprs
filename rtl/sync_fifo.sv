// =============================================================================
// sync_fifo.sv — Parameterized Synchronous FIFO (unchanged from v3.1)
// Standard pointer-based FIFO with w_rdy/r_rdy handshake
// =============================================================================
module sync_fifo #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 8
)(
    input  logic             clk,
    input  logic             rst,
    // Write port
    input  logic [WIDTH-1:0] w_data,
    input  logic             w_en,
    output logic             w_rdy,
    // Read port
    output logic [WIDTH-1:0] r_data,
    input  logic             r_en,
    output logic             r_rdy,
    // Status
    output logic [$clog2(DEPTH+1)-1:0] level
);

    localparam int PTR_W = $clog2(DEPTH);

    logic [WIDTH-1:0] mem [0:DEPTH-1];
    logic [PTR_W-1:0] wr_ptr, rd_ptr;
    logic [$clog2(DEPTH+1)-1:0] count;

    assign w_rdy  = (count < DEPTH);
    assign r_rdy  = (count > 0);
    assign r_data = mem[rd_ptr];
    assign level  = count;

    always_ff @(posedge clk) begin
        if (rst) begin
            wr_ptr <= '0;
            rd_ptr <= '0;
            count  <= '0;
        end else begin
            case ({w_en && w_rdy, r_en && r_rdy})
                2'b10: begin
                    mem[wr_ptr] <= w_data;
                    wr_ptr      <= (wr_ptr == DEPTH-1) ? '0 : wr_ptr + 1;
                    count       <= count + 1;
                end
                2'b01: begin
                    rd_ptr <= (rd_ptr == DEPTH-1) ? '0 : rd_ptr + 1;
                    count  <= count - 1;
                end
                2'b11: begin
                    mem[wr_ptr] <= w_data;
                    wr_ptr      <= (wr_ptr == DEPTH-1) ? '0 : wr_ptr + 1;
                    rd_ptr      <= (rd_ptr == DEPTH-1) ? '0 : rd_ptr + 1;
                    // count unchanged
                end
                default: ; // no-op
            endcase
        end
    end

endmodule
