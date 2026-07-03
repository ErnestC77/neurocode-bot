import { describe, expect, it } from "vitest";
import { resolveScreen } from "./resolveScreen";

describe("resolveScreen", () => {
  it("maps awaiting_consent to consent", () => {
    expect(resolveScreen("awaiting_consent", null)).toBe("consent");
  });

  it("maps in_test to quiz", () => {
    expect(resolveScreen("in_test", null)).toBe("quiz");
  });

  it("maps result_shown to result", () => {
    expect(resolveScreen("result_shown", "survival")).toBe("result");
  });

  it("maps offer_shown to offer", () => {
    expect(resolveScreen("offer_shown", "survival")).toBe("offer");
  });

  it("defaults unknown checkpoint without result to welcome", () => {
    expect(resolveScreen("new", null)).toBe("welcome");
  });

  it("falls back to offer for idle (post-purchase/post-lead) when result already exists", () => {
    // idle наступает после deliver()/create_lead — своего экрана не имеет,
    // Offer с available_products и есть умное меню M9.
    expect(resolveScreen("idle", "impostor")).toBe("offer");
  });

  it("maps practicum_viewed to product-detail", () => {
    expect(resolveScreen("practicum_viewed", "survival")).toBe("product-detail");
  });

  it("maps book_viewed to product-detail", () => {
    expect(resolveScreen("book_viewed", "survival")).toBe("product-detail");
  });

  it("maps consult_viewed to consult-detail", () => {
    expect(resolveScreen("consult_viewed", "survival")).toBe("consult-detail");
  });

  it("maps awaiting_email to consult-email-input", () => {
    expect(resolveScreen("awaiting_email", "survival")).toBe("consult-email-input");
  });
});
