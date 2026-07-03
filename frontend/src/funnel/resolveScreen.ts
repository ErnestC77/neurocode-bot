export type ScreenId =
  | "welcome"
  | "consent"
  | "quiz"
  | "result"
  | "offer"
  | "product-detail"
  | "consult-detail"
  | "consult-email-input";

export function resolveScreen(checkpoint: string, resultType: string | null): ScreenId {
  if (checkpoint === "awaiting_consent") return "consent";
  if (checkpoint === "in_test") return "quiz";
  if (checkpoint === "result_shown") return "result";
  if (checkpoint === "offer_shown") return "offer";
  if (checkpoint === "practicum_viewed" || checkpoint === "book_viewed") return "product-detail";
  if (checkpoint === "consult_viewed") return "consult-detail";
  if (checkpoint === "awaiting_email") return "consult-email-input";
  return resultType !== null ? "offer" : "welcome";
}
