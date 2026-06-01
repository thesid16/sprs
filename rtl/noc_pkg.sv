// =============================================================================
// noc_pkg.sv — Network-on-Chip Shared Types & Constants (v6.0)
//
// Defines the adjacency table type that makes topology a configuration
// parameter rather than a structural design artifact.
// =============================================================================
`ifndef NOC_PKG_SV
`define NOC_PKG_SV

package noc_pkg;

    // ── NoC Limits ──
    parameter int MAX_ROUTERS   = 4096;  // max routers in a system (supports G≤4096)
    parameter int MAX_PORTS     = 8;     // max ports per router
    parameter int NOC_FLIT_W    = 96;    // single-flit packets
    parameter int DEFAULT_VCS   = 2;     // default virtual channels per port
    parameter int MAX_VCS       = 4;     // max virtual channels per port

    // ── Adjacency Table Entry ──
    // For router R, port P: adj[R][P] = {target_router, target_port}
    // A value of ADJ_DISCONNECTED means the port is unused.
    parameter int ADJ_DISCONNECTED = 16'hFFFF;

    typedef struct packed {
        logic [11:0] target_router;  // 12-bit: supports up to 4096 routers
        logic [11:0] target_port;    // 12-bit: supports up to 4096 ports (future-proof)
    } adj_entry_t;

    // ── Packet Format (v8.0 RDMA-Push) ──
    // [95:80] dest_node_id  (16 bits) — target GPU (NoC routing)
    // [79:70] target_addr   (10 bits) — DMEM address at destination
    // [69:64] reserved      (6 bits)  — future use
    // [63:0]  payload       (64 bits) — data
    parameter int PKT_DEST_HI  = 95;
    parameter int PKT_DEST_LO  = 80;
    parameter int PKT_TADDR_HI = 79;
    parameter int PKT_TADDR_LO = 70;

endpackage

`endif
