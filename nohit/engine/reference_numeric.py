"""Independent scalar bone equations for optional typed reference execution.

These functions never call the native search library. The ordinary materialized
compiler retains its object equations as a differential oracle.
"""


def advance_bones(rows, count, dt):
    write = 0
    for read in range(count):
        x = rows[read, 0] + rows[read, 4] * dt
        y = rows[read, 1] + rows[read, 5] * dt
        if rows[read, 0] != x:
            rows[read, 0] = x
        if rows[read, 1] != y:
            rows[read, 1] = y
        direction = rows[read, 7]
        if ((direction == 0. and rows[read, 0] > 640.)
                or (direction == 1. and rows[read, 1] > 480.)
                or (direction == 2. and rows[read, 0] < -rows[read, 2])
                or (direction == 3. and rows[read, 1] < -rows[read, 3])):
            continue
        if write != read:
            for column in range(8):
                rows[write, column] = rows[read, column]
        write += 1
    return write


def bone_geometry(rows, count, bounds, white, blue):
    nw = nb = 0
    for read in range(count):
        x = rows[read, 0]
        y = rows[read, 1]
        right = x + rows[read, 2]
        bottom = y + rows[read, 3]
        left = right if right < x else x
        top = bottom if bottom < y else y
        right = right if right > x else x
        bottom = bottom if bottom > y else y
        if len(bounds) == 4 and not (left <= bounds[2] and right >= bounds[0]
                and top <= bounds[3] and bottom >= bounds[1]):
            continue
        if rows[read, 6] == 1.:
            blue[nb, 0] = left
            blue[nb, 1] = top
            blue[nb, 2] = right
            blue[nb, 3] = bottom
            nb += 1
        else:
            white[nw, 0] = left
            white[nw, 1] = top
            white[nw, 2] = right
            white[nw, 3] = bottom
            nw += 1
    return nw, nb
