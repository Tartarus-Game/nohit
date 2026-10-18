"""Differential correctness and collision throughput of two native code images.

Includes unordered/NaN boxes, boundary ULPs, stationary blue immunity and
offscreen queries. Times include the public ABI's index construction. These
are kernel measurements, not full-solver speedups.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import statistics
import time

import numpy as np


def bind(path):
    library = C.CDLL(str(path.resolve()))
    library.nohit_collision.argtypes = [C.c_void_p, C.c_int, C.c_void_p, C.c_int,
        C.c_void_p, C.c_int, C.c_void_p, C.c_int, C.c_void_p]
    library.nohit_collision.restype = C.c_int
    return library


def query(library, states, white, blue, polygons):
    output = np.empty(len(states), np.uint8)
    pointer = lambda a: C.c_void_p(a.ctypes.data)
    status = library.nohit_collision(pointer(states), len(states), pointer(white), len(white),
        pointer(blue), len(blue), pointer(polygons), len(polygons), pointer(output))
    assert status == 0
    return output


def scenes():
    rng = np.random.default_rng(7821)
    empty_boxes = np.empty((0, 4)); empty_polys = np.empty((0, 8))
    for count in (0, 1, 3, 4, 7, 8, 9, 15, 16, 17, 31, 64, 129):
        boxes = rng.uniform(-100, 700, (count, 4))
        boxes[:, 2:] = boxes[:, :2] + rng.uniform(-10, 90, (count, 2))
        if count >= 8:
            boxes[:5] = [[np.nan, 0., 100., 100.], [-np.inf, 300., 20., np.inf],
                         [100., 100., 100., 100.], [10., np.nan, 20., 30.], [-0., -0., 0., 0.]]
        states = np.zeros((2000, 11))
        states[:, :2] = rng.uniform(-100, 800, (len(states), 2))
        states[:, 2:4] = rng.choice([0., -0., 1., -1.], (len(states), 2))
        points = np.array([[98., 98.], [102., 102.], [-2., -2.], [2., 2.],
                           [0., 0.], [640., 480.], [114514., 1919.], [np.inf, np.inf]])
        points = np.concatenate([points, np.nextafter(points, -np.inf), np.nextafter(points, np.inf)])
        states[:len(points), :2] = points
        states[-2:, 10] = 1.
        yield f'boundaries-{count}', (states, boxes, boxes[::-1].copy(), empty_polys), False
    states = np.zeros((32768, 11)); states[:, :2] = rng.uniform([700, 500], [1200, 1000], (len(states), 2))
    states[:, 2] = 1.
    boxes = rng.uniform([0, 0, 0, 0], [640, 480, 640, 480], (256, 4))
    boxes[:, 2:] = boxes[:, :2] + 20.
    yield 'offscreen-256-rectangles', (states, boxes, empty_boxes, empty_polys), True
    states = states.copy(); states[:, :2] = rng.uniform([0, 0], [640, 480], (len(states), 2))
    yield 'indexed-256-rectangles', (states, boxes, empty_boxes, empty_polys), True
    polygons = []
    for angle in np.linspace(-np.pi, np.pi, 24):
        u = np.array([np.cos(angle), np.sin(angle)]); v = np.array([-u[1], u[0]])
        centre = rng.uniform([0, 0], [640, 480]); length = rng.uniform(20, 700); width = rng.uniform(0, 8)
        polygons.append(np.array([centre-u*length-v*width, centre-u*length+v*width,
                                  centre+u*length+v*width, centre+u*length-v*width]).reshape(8))
    yield 'indexed-24-quads', (states, empty_boxes, empty_boxes, np.array(polygons)), True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scalar', type=Path, required=True)
    parser.add_argument('--highway', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=9)
    args = parser.parse_args()
    libraries = [bind(args.scalar), bind(args.highway)]
    rows = []; total = 0
    for name, scene, timing in scenes():
        expected = query(libraries[0], *scene)
        actual = query(libraries[1], *scene)
        assert expected.tobytes() == actual.tobytes(), name
        total += len(expected)
        row = dict(case=name, queries=len(expected), exact_match=True)
        if timing:
            samples = [[], []]
            for repetition in range(args.repeats):
                for index in ((0, 1) if repetition % 2 == 0 else (1, 0)):
                    began = time.perf_counter(); result = query(libraries[index], *scene)
                    samples[index].append(time.perf_counter()-began)
                    assert result.tobytes() == expected.tobytes()
            row.update(scalar_seconds=statistics.median(samples[0]), highway_seconds=statistics.median(samples[1]), samples_seconds=samples)
            row['speedup'] = row['scalar_seconds'] / row['highway_seconds']
        rows.append(row)
    receipt = dict(scope='public collision ABI; not full solver', exact_queries=total,
        scalar_sha256=hashlib.sha256(args.scalar.read_bytes()).hexdigest(),
        highway_sha256=hashlib.sha256(args.highway.read_bytes()).hexdigest(), cases=rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(dict(exact_queries=total, timings=[r for r in rows if 'speedup' in r]), indent=2))


if __name__ == '__main__':
    main()
