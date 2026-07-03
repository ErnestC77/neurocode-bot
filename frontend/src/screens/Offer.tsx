import type { FunnelState } from "@/api/client";
import { OFFER_EMPTY_TEXT, OFFER_INTRO_TEXTS, PRODUCT_LABELS, RETAKE_BUTTON_LABEL } from "@/content/texts";

interface Props {
  state: FunnelState;
  onRetake: () => void;
}

function priceLabel(product: string, state: FunnelState): string {
  if (product === "book") return `${PRODUCT_LABELS.book} — ${state.book_price_rub} ₽`;
  if (product === "practicum") return `${PRODUCT_LABELS.practicum} — ${state.practicum_price_rub} ₽`;
  return PRODUCT_LABELS.consult;
}

export default function Offer({ state, onRetake }: Props) {
  const available = state.available_products ?? [];
  const resultType = state.result_type;

  return (
    <div className="flex min-h-screen flex-col bg-navy p-6 text-white">
      <div className="mb-4 whitespace-pre-line text-[15px] leading-relaxed">
        {available.length > 0 && resultType !== null ? OFFER_INTRO_TEXTS[resultType] : OFFER_EMPTY_TEXT}
      </div>
      <div className="flex flex-col gap-3">
        {available.map((product) => (
          <div
            key={product}
            className="rounded-xl border border-gold/40 bg-gold/10 px-4 py-3 text-sm font-semibold text-gold"
          >
            {priceLabel(product, state)}
          </div>
        ))}
      </div>
      <button onClick={onRetake} className="mt-auto pt-6 text-center text-sm text-gold/70 underline">
        {RETAKE_BUTTON_LABEL}
      </button>
    </div>
  );
}
