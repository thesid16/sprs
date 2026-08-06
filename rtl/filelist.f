# Compile order matters: SystemVerilog packages must be analysed before any
# module that imports them. An alphabetical glob (rtl/*.sv) puts
# btree_fsm_fast.sv ahead of btree_pkg.sv and fails with
#   ERROR: [VRFC 10-2989] 'btree_pkg' is not declared
# Always drive the tools from this list.
noc_pkg.sv
btree_pkg.sv
sync_fifo.sv
link_tx.sv
noc_link.sv
noc_router.sv
noc_ni.sv
fp64_add.sv
btree_fsm_fast.sv
noc_system.sv
