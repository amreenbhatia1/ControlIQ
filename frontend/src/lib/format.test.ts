import { describe, expect, it } from "vitest";
import { formatBytes, formatDate, formatDateTime, relativeTime, scoreColor, SEVERITY_COLORS, shortHash, titleCase } from "./format";

describe("date formatting", () => {
  it("formats in UTC regardless of the local timezone", () => {
    expect(formatDate("2026-10-29T23:30:00Z")).toBe("29 Oct 2026");
    expect(formatDateTime("2026-10-29T15:28:00Z")).toBe("29 Oct 2026, 15:28 UTC");
  });

  it("returns a dash for missing or invalid values", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("not a date")).toBe("—");
    expect(formatDateTime(undefined)).toBe("—");
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-10-29T15:00:00Z");

  it("describes past and future offsets", () => {
    expect(relativeTime("2026-10-29T14:59:30Z", now)).toBe("just now");
    expect(relativeTime("2026-10-29T14:58:00Z", now)).toBe("2 minutes ago");
    expect(relativeTime("2026-10-28T15:00:00Z", now)).toBe("1 day ago");
    expect(relativeTime("2026-10-30T15:00:00Z", now)).toBe("in 1 day");
  });

  it("handles missing values", () => {
    expect(relativeTime(null, now)).toBe("never");
    expect(relativeTime("garbage", now)).toBe("—");
  });
});

describe("misc formatting", () => {
  it("formats byte sizes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1356)).toBe("1.3 KB");
    expect(formatBytes(2 * 1024 * 1024)).toBe("2.00 MB");
  });

  it("shortens hashes only when needed", () => {
    expect(shortHash("abcdef", 12)).toBe("abcdef");
    expect(shortHash("2aba91260a4c04bcb6d8", 12)).toBe("2aba91260a4c…");
  });

  it("title-cases snake_case keys", () => {
    expect(titleCase("business_service_criticality")).toBe("Business Service Criticality");
  });

  it("maps scores onto severity colours using default bands", () => {
    expect(scoreColor(90)).toBe(SEVERITY_COLORS.Critical);
    expect(scoreColor(60)).toBe(SEVERITY_COLORS.High);
    expect(scoreColor(40)).toBe(SEVERITY_COLORS.Medium);
    expect(scoreColor(10)).toBe(SEVERITY_COLORS.Low);
  });
});
