import { describe, expect, it } from "vitest";

import {
  accentFromSignedDecimal,
  computeEquityYDomain,
  formatDecimalDisplay,
  formatEquityAxisTick,
  formatMoneyDisplay,
  parseDecimalForChart,
  toFiniteNumber,
} from "../../src/lib/dashboard/formatters";

describe("toFiniteNumber", () => {
  it("parses string, number, and Decimal-like inputs", () => {
    expect(toFiniteNumber("12.5")).toBe(12.5);
    expect(toFiniteNumber(12.5)).toBe(12.5);
    expect(toFiniteNumber({ toString: () => "42.25" })).toBe(42.25);
  });

  it("rejects null, undefined, empty, invalid, NaN, Infinity", () => {
    expect(toFiniteNumber(null)).toBeNull();
    expect(toFiniteNumber(undefined)).toBeNull();
    expect(toFiniteNumber("")).toBeNull();
    expect(toFiniteNumber("   ")).toBeNull();
    expect(toFiniteNumber("not-a-number")).toBeNull();
    expect(toFiniteNumber(Number.NaN)).toBeNull();
    expect(toFiniteNumber(Number.POSITIVE_INFINITY)).toBeNull();
    expect(toFiniteNumber(Number.NEGATIVE_INFINITY)).toBeNull();
  });

  it("normalizes negative zero and scientific notation", () => {
    expect(toFiniteNumber(-0)).toBe(0);
    expect(Object.is(toFiniteNumber(-0), -0)).toBe(false);
    expect(toFiniteNumber("0E-18")).toBe(0);
    expect(toFiniteNumber("-0E-18")).toBe(0);
    expect(toFiniteNumber("1.5e2")).toBe(150);
  });
});

describe("formatMoneyDisplay (en-US)", () => {
  it("formats grouped money with two fraction digits", () => {
    expect(formatMoneyDisplay("100000.000000")).toBe("$100,000.00");
    expect(formatMoneyDisplay(100000)).toBe("$100,000.00");
    expect(formatMoneyDisplay("10.00")).toBe("$10.00");
  });

  it("handles scientific notation, negative zero, and tiny residues", () => {
    expect(formatMoneyDisplay("0E-18")).toBe("$0.00");
    expect(formatMoneyDisplay("-0E-18")).toBe("$0.00");
    expect(formatMoneyDisplay(-0)).toBe("$0.00");
  });

  it("formats negative PnL and rounds fraction digits", () => {
    expect(formatMoneyDisplay("-715.115")).toBe("-$715.12");
    expect(formatMoneyDisplay("-715.114")).toBe("-$715.11");
    expect(formatMoneyDisplay("-42.50")).toBe("-$42.50");
  });

  it("returns unavailable for invalid inputs", () => {
    expect(formatMoneyDisplay(null)).toBe("—");
    expect(formatMoneyDisplay(undefined)).toBe("—");
    expect(formatMoneyDisplay("abc")).toBe("—");
    expect(formatMoneyDisplay(Number.NaN)).toBe("—");
    expect(formatMoneyDisplay(Number.POSITIVE_INFINITY)).toBe("—");
  });
});

describe("formatDecimalDisplay (en-US)", () => {
  it("formats quantities without inventing trailing zeros", () => {
    expect(formatDecimalDisplay("1234.5")).toBe("1,234.5");
    expect(formatDecimalDisplay("0.5")).toBe("0.5");
    expect(formatDecimalDisplay("100000.000000")).toBe("100,000");
  });

  it("collapses scientific tiny residues to zero", () => {
    expect(formatDecimalDisplay("0E-18")).toBe("0");
    expect(formatDecimalDisplay("-0E-18")).toBe("0");
  });

  it("returns unavailable for invalid inputs", () => {
    expect(formatDecimalDisplay(null)).toBe("—");
    expect(formatDecimalDisplay("nope")).toBe("—");
  });
});

describe("parseDecimalForChart", () => {
  it("accepts scientific notation and rejects invalid values", () => {
    expect(parseDecimalForChart("0E-18")).toBe(0);
    expect(parseDecimalForChart("-0E-18")).toBe(0);
    expect(parseDecimalForChart("12.5")).toBe(12.5);
    expect(parseDecimalForChart("not-a-number")).toBeNull();
    expect(parseDecimalForChart(null)).toBeNull();
  });
});

describe("accentFromSignedDecimal", () => {
  it("uses numeric sign including scientific and negative zero", () => {
    expect(accentFromSignedDecimal("12.5")).toBe("mint");
    expect(accentFromSignedDecimal("-3.25")).toBe("danger");
    expect(accentFromSignedDecimal("-0.00")).toBe("mint");
    expect(accentFromSignedDecimal("-0E-18")).toBe("mint");
    expect(accentFromSignedDecimal(null)).toBe("default");
    expect(accentFromSignedDecimal("bad")).toBe("default");
  });
});

describe("equity axis formatting (absolute equity)", () => {
  it("keeps distinct ticks for a tight ~100000 range", () => {
    const domain = computeEquityYDomain([99950, 100050]);
    const ticks = [99950, 100000, 100050].map((v) =>
      formatEquityAxisTick(v, domain),
    );
    expect(new Set(ticks).size).toBe(3);
    expect(ticks.every((t) => t.includes("100") || t.includes("99"))).toBe(
      true,
    );
    expect(ticks.some((t) => /0\.0k/.test(t))).toBe(false);
    expect(ticks.every((t) => !t.includes("NaN") && !t.includes("Infinity"))).toBe(
      true,
    );
  });

  it("formats flat equity without collapsing labels", () => {
    const domain = computeEquityYDomain([100000, 100000, 100000]);
    expect(domain[1]).toBeGreaterThan(domain[0]);
    const tick = formatEquityAxisTick(100000, domain);
    expect(tick).toMatch(/^\$100,000(\.00)?$/);
  });

  it("formats negative change ticks distinctly", () => {
    const domain = computeEquityYDomain([100500, 99500]);
    const high = formatEquityAxisTick(100500, domain);
    const low = formatEquityAxisTick(99500, domain);
    expect(high).not.toBe(low);
    expect(high.startsWith("$")).toBe(true);
    expect(low.startsWith("$")).toBe(true);
  });

  it("uses compact k labels only on wide domains", () => {
    const domain = computeEquityYDomain([10000, 200000]);
    const tick = formatEquityAxisTick(100000, domain);
    expect(tick).toMatch(/^\$\d+(\.\d+)?k$/);
  });
});
