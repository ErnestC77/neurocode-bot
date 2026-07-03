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

  it("falls back to offer for out-of-2a-scope checkpoints when result already exists", () => {
    // practicum_viewed/consult_viewed/book_viewed/idle принадлежат подпроекту 2b —
    // у 2a для них нет экрана; если результат уже есть, Offer самодостаточен.
    expect(resolveScreen("practicum_viewed", "impostor")).toBe("offer");
  });
});
