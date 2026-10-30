import { describe, expect, it } from "vitest";
import { buildUrl } from "./api";

describe("buildUrl", () => {
  it("prefixes the versioned API path", () => {
    expect(buildUrl("/findings")).toBe("/api/v1/findings");
  });

  it("omits empty, null and undefined parameters", () => {
    expect(buildUrl("/findings", { q: "", status: null, owner: undefined, page: 2 })).toBe("/api/v1/findings?page=2");
  });

  it("repeats array parameters and encodes values", () => {
    expect(buildUrl("/findings", { severity: ["Critical", "High"], q: "MFA & admin" })).toBe(
      "/api/v1/findings?severity=Critical&severity=High&q=MFA+%26+admin",
    );
  });

  it("serialises booleans and zero", () => {
    expect(buildUrl("/evidence", { uploaded_only: true, page: 0 })).toBe("/api/v1/evidence?uploaded_only=true&page=0");
  });
});
