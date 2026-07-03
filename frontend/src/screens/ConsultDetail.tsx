import { CONSULT_BOOK_BUTTON_LABEL, CONSULT_INTRO_TEXT } from "@/content/texts";

interface Props {
  onBook: () => void;
}

export default function ConsultDetail({ onBook }: Props) {
  return (
    <div className="flex min-h-screen flex-col justify-between bg-navy p-6 text-white">
      <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
        {CONSULT_INTRO_TEXT}
      </div>
      <button
        onClick={onBook}
        className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
      >
        {CONSULT_BOOK_BUTTON_LABEL}
      </button>
    </div>
  );
}
