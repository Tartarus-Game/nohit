// Per-lane binary64 predicates: no reassociation, FMA or approximate math.
// This is included only by the vcpkg/Highway build; the scalar kernel remains
// available as an independent differential oracle.
#pragma once
#include <hwy/highway.h>

namespace nohit_simd {
namespace hn = hwy::HWY_NAMESPACE;

inline bool rectangles_hit(const double* boxes, int count, double x, double y) {
    const hn::ScalableTag<double> d;
    const size_t lanes = hn::Lanes(d);
    const auto left = hn::Set(d, x - 2.), right = hn::Set(d, x + 2.);
    const auto top = hn::Set(d, y - 2.), bottom = hn::Set(d, y + 2.);
    int i = 0;
    for (; size_t(count - i) >= lanes; i += int(lanes)) {
        hn::Vec<decltype(d)> l, t, r, b;
        hn::LoadInterleaved4(d, boxes + size_t(i) * 4, l, t, r, b);
        const auto hit = hn::And(hn::And(hn::Ge(right, l), hn::Le(left, r)),
                                 hn::And(hn::Ge(bottom, t), hn::Le(top, b)));
        if (!hn::AllFalse(d, hit)) return true;
    }
    for (; i < count; ++i) {
        const double* b = boxes + size_t(i) * 4;
        if (x + 2. >= b[0] && x - 2. <= b[2] && y + 2. >= b[1] && y - 2. <= b[3]) return true;
    }
    return false;
}

} // namespace nohit_simd
