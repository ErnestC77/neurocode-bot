export type ScreenId = "welcome" | "consent" | "quiz" | "result" | "offer";

export function resolveScreen(checkpoint: string, resultType: string | null): ScreenId {
  if (checkpoint === "awaiting_consent") return "consent";
  if (checkpoint === "in_test") return "quiz";
  if (checkpoint === "result_shown") return "result";
  if (checkpoint === "offer_shown") return "offer";
  return resultType !== null ? "offer" : "welcome";
}
