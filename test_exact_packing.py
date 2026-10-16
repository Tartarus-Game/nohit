def pack_test(x, y, vy_tenth, kappa, tau):
    vy_offset = (int(vy_tenth) + 250) & 0x1FF
    return int(
        (int(x) & 0x1FF)
        | ((int(y) & 0xFF) << 9)
        | (vy_offset << 17)
        | ((int(kappa) & 0x01) << 26)
        | ((int(tau) & 0x1F) << 27)
    )

def unpack_test(p):
    p = int(p)
    x = p & 0x1FF
    y = (p >> 9) & 0xFF
    vy_tenth = int((p >> 17) & 0x1FF) - 250
    kappa = (p >> 26) & 0x01
    tau = (p >> 27) & 0x1F
    return (x, y, vy_tenth, kappa, tau)

# Test cases
test_cases = [
    (0, 0, 0, 1, 0),
    (349, 114, 60, 0, 1),
    (511, 255, -250, 0, 31),
    (146, 75, -2, 0, 15),
    (200, 50, -120, 0, 8),
]

for tc in test_cases:
    packed = pack_test(*tc)
    assert packed < 2**32, f"Packed exceeds 32 bits: {packed}"
    unpacked = unpack_test(packed)
    assert unpacked == tc, f"Mismatch: expected {tc}, got {unpacked}"
    print(f"PASS: {tc} -> 0x{packed:08X} -> {unpacked}")

print("\nALL PACKING TESTS PASSED!")
