import { describe, expect, it } from "vitest";
import { heatCells, inDirection, lineIsValid, nearFirstPoint, nextId, polygonArea, toNormalized, zoneIsValid } from "../src/geometry";

describe("toNormalized", () => {
  const rect = { left: 100, top: 50, width: 400, height: 200 };
  it("maps pointer to 0-1 and clamps outside the picture", () => {
    expect(toNormalized(300, 150, rect)).toEqual([0.5, 0.5]);
    expect(toNormalized(0, 0, rect)).toEqual([0, 0]);
    expect(toNormalized(9999, 9999, rect)).toEqual([1, 1]);
  });
  it("does not divide by zero for a hidden image", () => {
    expect(toNormalized(10, 10, { left: 0, top: 0, width: 0, height: 0 })).toEqual([0, 0]);
  });
});

describe("inDirection (must agree with the edge agent: 'left' of p1->p2 on screen)", () => {
  it("left-to-right line: left side is UP, so 'in' points up (negative y)", () => {
    const v = inDirection({ p1: [0, 0.5], p2: [1, 0.5], in_side: "left" });
    expect(v[0]).toBeCloseTo(0);
    expect(v[1]).toBeCloseTo(-1);
  });
  it("right side flips it", () => {
    const v = inDirection({ p1: [0, 0.5], p2: [1, 0.5], in_side: "right" });
    expect(v[1]).toBeCloseTo(1);
  });
  it("downward line: left of a line pointing down is to screen-right (+x)", () => {
    const v = inDirection({ p1: [0.5, 0], p2: [0.5, 1], in_side: "left" });
    expect(v[0]).toBeCloseTo(1);
    expect(v[1]).toBeCloseTo(0);
  });
});

describe("validity", () => {
  it("rejects zero-length lines and degenerate zones", () => {
    expect(lineIsValid({ p1: [0.5, 0.5], p2: [0.5, 0.5] })).toBe(false);
    expect(lineIsValid({ p1: [0.1, 0.1], p2: [0.9, 0.1] })).toBe(true);
    expect(zoneIsValid({ polygon: [[0, 0], [1, 1]] })).toBe(false);
    expect(zoneIsValid({ polygon: [[0, 0], [0.5, 0.5], [1, 1]] })).toBe(false); // collinear: no area
    expect(zoneIsValid({ polygon: [[0, 0], [1, 0], [1, 1]] })).toBe(true);
  });
  it("computes polygon area", () => {
    expect(polygonArea([[0, 0], [1, 0], [1, 1], [0, 1]])).toBeCloseTo(1);
  });
});

describe("helpers", () => {
  it("nextId skips used ids", () => {
    expect(nextId("line", [])).toBe("line1");
    expect(nextId("line", [{ id: "line1" }, { id: "line3" }])).toBe("line2");
  });
  it("closes a polygon only when near the first point and with 3+ points", () => {
    const poly: [number, number][] = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5]];
    expect(nearFirstPoint(poly, [0.102, 0.1], { width: 1000, height: 500 })).toBe(true);
    expect(nearFirstPoint(poly, [0.3, 0.3], { width: 1000, height: 500 })).toBe(false);
    expect(nearFirstPoint(poly.slice(0, 2), [0.1, 0.1], { width: 1000, height: 500 })).toBe(false);
  });
  it("turns sparse heat cells into rectangles scaled to the busiest cell", () => {
    const rects = heatCells([4, 2], { "0": 2, "5": 4 });
    expect(rects).toEqual([
      { x: 0, y: 0, w: 0.25, h: 0.5, opacity: 0.5, count: 2 },
      { x: 0.25, y: 0.5, w: 0.25, h: 0.5, opacity: 1, count: 4 },
    ]);
  });
});
