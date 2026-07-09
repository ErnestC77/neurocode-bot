import { BACK_TO_OFFER_LABEL, CONSULT_BOOK_BUTTON_LABEL, CONSULT_INTRO_TEXT } from "@/content/texts";

interface Props {
  onBook: () => void;
  onBack: () => void;
}

export default function ConsultDetail({ onBook, onBack }: Props) {
  return (
    <div className="flex min-h-screen flex-col justify-between bg-navy p-6 text-white">
      <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
        {CONSULT_INTRO_TEXT}
      </div>
      <div>
        <button
          onClick={onBook}
          className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
        >
          {CONSULT_BOOK_BUTTON_LABEL}
        </button>
        <button onClick={onBack} className="mt-4 w-full text-center text-sm text-gold/70 underline">
          {BACK_TO_OFFER_LABEL}
        </button>
      </div>
    </div>
  );
}
