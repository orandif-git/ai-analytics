Point = tuple[float, float]


def _side(p1: Point, p2: Point, pt: Point) -> float:
    """>0 when pt is on the RIGHT of the directed line p1->p2 as seen on screen (image y axis points down)."""
    return (p2[0] - p1[0]) * (pt[1] - p1[1]) - (p2[1] - p1[1]) * (pt[0] - p1[0])


def crossing(p1: Point, p2: Point, prev: Point, cur: Point) -> str | None:
    """Return 'left_to_right' / 'right_to_left' when the move prev->cur crosses the SEGMENT p1-p2, else None."""
    s_prev, s_cur = _side(p1, p2, prev), _side(p1, p2, cur)
    if s_prev == 0 or s_cur == 0 or (s_prev > 0) == (s_cur > 0):
        # On the line counts as not yet crossed; the next frame decides.
        return None
    # The movement must cross within the segment, not its infinite extension.
    if (_side(prev, cur, p1) > 0) == (_side(prev, cur, p2) > 0):
        return None
    return "right_to_left" if s_prev > 0 else "left_to_right"


def point_in_polygon(pt: Point, polygon: list[Point]) -> bool:
    x, y = pt
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside
