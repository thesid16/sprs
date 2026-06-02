// =============================================================================
// btree_pkg.sv — Shared Parameters, Types, and Opcodes
// Binary Tree Reduction FSM v4.1
// CHANGES from v4.0:
//   - 16-bit DMEM addresses (was 8-bit, now supports 65K entries)
//   - 96-bit packets with dest_gpu field
//   - ALU operation field in instruction
//   - Performance counter types
// =============================================================================
`ifndef BTREE_PKG_SV
`define BTREE_PKG_SV

package btree_pkg;

    // =========================================================================
    // Configuration Parameters
    // =========================================================================
    parameter int DMEM_DEPTH     = 512;
    parameter int IMEM_DEPTH     = 512;
    parameter int TX_BUF_DEPTH   = 8;
    parameter int RX_BUF_DEPTH   = 8;
    parameter int TIMEOUT_MAX    = 10000;
    parameter int WATCHDOG_MAX   = 20000;

    // =========================================================================
    // Opcode Definitions (v4.1 ISA)
    // =========================================================================
    typedef enum logic [3:0] {
        OP_NOP      = 4'h0,
        OP_GENERATE = 4'h1,
        OP_COMPUTE  = 4'h2,
        OP_SEND     = 4'h3,
        OP_RESERVED = 4'h4   // was OP_RECV, deprecated in RDMA-Push v8
    } opcode_t;

    // =========================================================================
    // ALU Operation Encoding (3 bits in aux field)
    // =========================================================================
    typedef enum logic [2:0] {
        ALU_ADD  = 3'b000,
        ALU_MAX  = 3'b001,
        ALU_MIN  = 3'b010,
        ALU_AND  = 3'b011,
        ALU_OR   = 3'b100,
        ALU_XOR  = 3'b101,
        ALU_SADD = 3'b110,  // Signed 64-bit addition (two's complement)
        ALU_FADD = 3'b111   // IEEE 754 double-precision floating-point addition
    } alu_op_t;

    // =========================================================================
    // Instruction Format (64-bit word)
    //   [63:60] opcode    (4 bits)
    //   [59:56] aux       (4 bits) — aux[0]=link, aux[3:1]=alu_op
    //   [55:40] dest      (16 bits) — DMEM dest (COMPUTE/GEN), target_addr (SEND)
    //   [39:24] addr_a    (16 bits) — DMEM source address A
    //   [23:8]  addr_b    (16 bits) — DMEM source address B / dest_gpu (SEND)
    //   [7:0]   reserved  (8 bits) — future use
    // For SEND: dest = target_addr at receiver, addr_a = local DMEM source,
    //           addr_b = dest_gpu_id (NoC routing)
    // =========================================================================

    // =========================================================================
    // Packet Format (96-bit, v8.0 RDMA-Push)
    //   [95:80] dest_gpu_id  (16 bits) — target GPU (NoC routing)
    //   [79:70] target_addr  (10 bits) — DMEM address at destination
    //   [69:64] reserved     (6 bits)  — future use
    //   [63:0]  payload      (64 bits) — data
    // =========================================================================
    parameter int PKT_TOTAL_W = 96;

    // =========================================================================
    // FSM States (7 states)
    // =========================================================================
    typedef enum logic [3:0] {
        S_IDLE    = 4'd0,
        S_FETCH   = 4'd1,
        S_DECODE  = 4'd2,
        S_EXEC    = 4'd3,
        S_WBACK   = 4'd4,
        S_DONE    = 4'd5,
        S_ERROR   = 4'd6
    } fsm_state_t;

    // =========================================================================
    // Fat Tree / Switch Parameters (v4.2)
    // =========================================================================
    parameter int MAX_PORTS        = 4;      // max switch radix
    parameter int SWITCH_BUF_DEPTH = 16;     // per-port FIFO depth in switches
    parameter int ROUTE_TABLE_DEPTH = 4096;  // entries in routing tables (supports G≤4096)

    // =========================================================================
    // Helper Functions
    // =========================================================================
    function automatic int clog2_safe(input int val);
        if (val <= 1) return 1;
        else return $clog2(val);
    endfunction

endpackage

`endif
