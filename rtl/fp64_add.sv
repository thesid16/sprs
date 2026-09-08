// =============================================================================
// fp64_add.sv — Combinational IEEE 754 Double-Precision Floating-Point Adder
//
// Fully combinational (no clock). Computes result = a + b in one cycle.
//
// IEEE 754 double-precision format (64 bits):
//   [63]      sign     (1 bit)
//   [62:52]   exponent (11 bits, biased by 1023)
//   [51:0]    fraction (52 bits, implicit leading 1 for normals)
//
// Supported:
//   - Normal + Normal
//   - Normal + Zero, Zero + Normal, Zero + Zero
//   - Subnormal inputs treated as zero (flush-to-zero input)
//   - Subnormal results flushed to zero (flush-to-zero output)
//   - Inf + Inf (same sign) = Inf
//   - Inf + Inf (different sign) = NaN
//   - NaN propagation (any NaN input → NaN output)
//   - Inf + finite = Inf
//   - Negative numbers fully supported (sign-magnitude arithmetic)
//
// Not supported (out of scope for reduction tree):
//   - Rounding modes other than round-to-nearest-even
//   - Denormalized (subnormal) intermediate results
//   - Tininess detection / underflow flags
//   - Signaling NaN vs quiet NaN distinction
// =============================================================================
`timescale 1ns / 1ps

module fp64_add (
    input  logic [63:0] a,
    input  logic [63:0] b,
    output logic [63:0] result
);

    // ── Unpack ──
    logic        a_sign, b_sign;
    logic [10:0] a_exp,  b_exp;
    logic [51:0] a_frac, b_frac;

    assign a_sign = a[63];
    assign a_exp  = a[62:52];
    assign a_frac = a[51:0];
    assign b_sign = b[63];
    assign b_exp  = b[62:52];
    assign b_frac = b[51:0];

    // ── Special value detection ──
    logic a_is_zero, b_is_zero;
    logic a_is_inf,  b_is_inf;
    logic a_is_nan,  b_is_nan;
    logic a_is_sub,  b_is_sub;

    assign a_is_zero = (a_exp == 11'd0) && (a_frac == 52'd0);
    assign b_is_zero = (b_exp == 11'd0) && (b_frac == 52'd0);
    assign a_is_inf  = (a_exp == 11'h7FF) && (a_frac == 52'd0);
    assign b_is_inf  = (b_exp == 11'h7FF) && (b_frac == 52'd0);
    assign a_is_nan  = (a_exp == 11'h7FF) && (a_frac != 52'd0);
    assign b_is_nan  = (b_exp == 11'h7FF) && (b_frac != 52'd0);
    assign a_is_sub  = (a_exp == 11'd0) && (a_frac != 52'd0);
    assign b_is_sub  = (b_exp == 11'd0) && (b_frac != 52'd0);

    // ── Main addition logic ──
    always_comb begin
        // Default: NaN
        result = {1'b0, 11'h7FF, 1'b1, 51'd0};  // canonical quiet NaN

        // NaN propagation
        if (a_is_nan) begin
            result = {a[63], 11'h7FF, 1'b1, a_frac[50:0]};
        end else if (b_is_nan) begin
            result = {b[63], 11'h7FF, 1'b1, b_frac[50:0]};
        end
        // Inf handling
        else if (a_is_inf && b_is_inf) begin
            if (a_sign == b_sign)
                result = {a_sign, 11'h7FF, 52'd0};  // same sign → Inf
            else
                result = {1'b0, 11'h7FF, 1'b1, 51'd0};  // Inf - Inf → NaN
        end else if (a_is_inf) begin
            result = a;
        end else if (b_is_inf) begin
            result = b;
        end
        // Zero / subnormal handling (flush-to-zero for subnormals)
        else if ((a_is_zero || a_is_sub) && (b_is_zero || b_is_sub)) begin
            result = 64'd0;
        end else if (a_is_zero || a_is_sub) begin
            result = b;
        end else if (b_is_zero || b_is_sub) begin
            result = a;
        end
        // Normal + Normal
        else begin
            // Build mantissas with implicit leading 1 (54 bits: guard + 53-bit mantissa)
            logic [54:0] m_a, m_b;  // 55 bits: 1 overflow + 1 implicit + 52 frac + 1 guard
            logic [10:0] e_a, e_b, e_diff, e_r;
            logic        s_a, s_b, s_r;
            logic [54:0] m_big, m_small, m_aligned;
            logic [10:0] shift_amt;
            logic        sticky;   // OR of all bits shifted out during alignment
            logic        align_round;  // MSB of the alignment tail (weight 1/2 guard-unit)
            logic        align_low;    // OR of the alignment tail below align_round
            logic        sub_borrow;   // effective subtraction consumed a borrow
            logic        effective_sub;
            logic [55:0] m_sum;  // 56 bits for possible carry
            logic [54:0] m_norm;
            logic [10:0] e_norm;
            int           lzc;

            e_a = a_exp;
            e_b = b_exp;

            // Determine which operand has larger exponent
            if (e_a >= e_b) begin
                s_a = a_sign; s_b = b_sign;
                m_big   = {1'b0, 1'b1, a_frac, 1'b0};  // [54:0] = 0.1.frac.guard
                m_small = {1'b0, 1'b1, b_frac, 1'b0};
                e_r = e_a;
                shift_amt = e_a - e_b;
            end else begin
                s_a = b_sign; s_b = a_sign;
                m_big   = {1'b0, 1'b1, b_frac, 1'b0};
                m_small = {1'b0, 1'b1, a_frac, 1'b0};
                e_r = e_b;
                shift_amt = e_b - e_a;
            end

            // Align mantissas (right-shift smaller by exponent difference)
            // Track sticky bit: OR of all bits shifted out
            // The tail is split into its MSB (align_round, weight 1/2 of a guard
            // unit) and everything below it (align_low).  sticky is their OR and
            // is bit-identical to the previous single-expression form; the split
            // is what makes the effective-subtraction borrow roundable.
            if (shift_amt > 11'd54) begin
                m_aligned   = 55'd0;
                align_round = 1'b0;                // m_small[54:] is zero, so bit
                align_low   = |m_small;            // shift_amt-1 >= 54 is zero too
            end else if (shift_amt == 11'd0) begin
                m_aligned   = m_small;
                align_round = 1'b0;
                align_low   = 1'b0;
            end else begin
                m_aligned   = m_small >> shift_amt;
                align_round = m_small[shift_amt - 11'd1];
                align_low   = |(m_small & ~({55{1'b1}} << (shift_amt - 11'd1)));
            end
            sticky = align_round | align_low;

            // Effective operation
            effective_sub = (s_a != s_b);

            sub_borrow = 1'b0;
            if (!effective_sub) begin
                // Same sign: add mantissas
                m_sum = {1'b0, m_big} + {1'b0, m_aligned};
                s_r = s_a;
            end else begin
                // Different signs: subtract (big - aligned, big is always >= aligned).
                // The bits truncated during alignment form a tail 0 < t < 1 guard
                // unit whenever sticky=1.  The exact difference is
                //     m_big - m_aligned - t
                // so the raw m_big - m_aligned is too large by t and the ADDITION
                // rounding rule below (guard && (sticky || lsb)) then rounds a
                // value lying just BELOW the midpoint up, giving +1 ulp.  Borrow
                // the tail here: the remainder becomes r = 1 - t, still strictly
                // inside (0,1), so sticky stays 1 and the same rounding rule is
                // now the correct one.
                sub_borrow = sticky;
                m_sum = {1'b0, m_big} - {1'b0, m_aligned} - {55'd0, sticky};
                s_r = s_a;
                // If result is negative (shouldn't happen since big >= small in magnitude)
                // but handle exponent-equal case where fractions may differ
                if (m_sum[55]) begin
                    m_sum = ~m_sum + 56'd1;  // negate
                    s_r = !s_a;
                end
            end

            // Check for zero result
            if (m_sum == 56'd0) begin
                result = 64'd0;
            end else begin
                // Normalize
                e_norm = e_r;
                m_norm = m_sum[54:0];

                // Overflow: carry out from mantissa addition
                // Bit 54 overflow is the common case (e.g. 1.0+1.0)
                // Bit 55 overflow can occur with extreme carry chains
                if (m_sum[55]) begin
                    // Right-shift by 2: bit [0] → sticky, bit [1] → new guard
                    sticky = sticky | m_sum[0];
                    m_norm = {m_sum[55:2], m_sum[1]};
                    e_norm = e_r + 11'd2;
                end else if (m_sum[54]) begin
                    // Right-shift by 1: bit [0] shifted out → accumulate into sticky
                    sticky = sticky | m_sum[0];
                    m_norm = m_sum[55:1];
                    e_norm = e_r + 11'd1;
                end else begin
                    // Find leading one and shift left
                    // The leading 1 should be at bit 53 (position of implicit 1)
                    lzc = 0;
                    for (int i = 54; i >= 0; i--) begin
                        if (m_sum[i]) break;
                        lzc++;
                    end
                    // Shift needed to place leading 1 at bit 53
                    // m_sum bit 54 = overflow (not set here), bit 53 = implicit 1 position
                    if (lzc > 0) begin
                        // Leading one is at bit (54-lzc), need it at bit 53
                        // Shift left by (lzc - 1) if lzc >= 1
                        if (lzc <= 1) begin
                            m_norm = m_sum[54:0];
                        end else begin
                            if (lzc - 1 < 55)
                                m_norm = m_sum[54:0] << (lzc - 1);
                            else
                                m_norm = 55'd0;
                            // When a borrow was taken the remainder is r = 1 - t.
                            // A left shift by one scales it to 2r, which leaves
                            // (0,1) whenever t <= 1/2, i.e. whenever the tail is
                            // not strictly greater than half a guard unit.  Carry
                            // that whole unit into m_norm and recompute whether
                            // anything is left below.  (For effective subtraction
                            // a borrow implies m_sum >= 2^52, so lzc is 1 or 2 and
                            // this is the only shift amount that can occur.)
                            if (sub_borrow && (lzc == 2)) begin
                                if (!(align_round && align_low))
                                    m_norm = m_norm + 55'd1;   // 2r >= 1
                                sticky = !(align_round && !align_low); // 2r-carry != 0
                            end
                            if (e_norm > (lzc - 1))
                                e_norm = e_norm - (lzc - 1);
                            else begin
                                // Underflow → flush to zero
                                result = {s_r, 11'd0, 52'd0};
                                m_norm = 55'd0;  // suppress further packing
                                e_norm = 11'd0;
                            end
                        end
                    end
                end

                // Check for overflow to infinity
                if (e_norm >= 11'h7FF) begin
                    result = {s_r, 11'h7FF, 52'd0};  // Infinity
                end else if (m_norm != 55'd0) begin
                    // Pack: extract fraction (bits 52:1 of m_norm, bit 53 is implicit 1)
                    // Round: bit 0 of m_norm is guard bit
                    logic [51:0] frac_out;
                    logic        guard;
                    frac_out = m_norm[52:1];
                    guard    = m_norm[0];
                    // Round to nearest even (IEEE 754)
                    // Round up when: guard && (sticky || frac_out[0])
                    // - guard=1, sticky=1 → always round up (away from exact midpoint)
                    // - guard=1, sticky=0 → tie: round to even (up if frac_out[0]=1)
                    if (guard && (sticky || frac_out[0])) begin
                        frac_out = frac_out + 52'd1;
                        if (frac_out == 52'd0) begin
                            // Fraction overflow from rounding
                            e_norm = e_norm + 11'd1;
                        end
                    end
                    if (e_norm >= 11'h7FF)
                        result = {s_r, 11'h7FF, 52'd0};
                    else
                        result = {s_r, e_norm, frac_out};
                end
            end
        end
    end

endmodule
