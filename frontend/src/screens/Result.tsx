import { RESULT_LABELS, RESULT_NEXT_BUTTON_LABEL, RESULT_TEXTS } from "@/content/texts";

interface Props {
  resultType: string;
  onNext: () => void;
}

export default function Result({ resultType, onNext }: Props) {
  return (
    <div className="flex min-h-screen flex-col bg-navy p-6 text-white">
      <div className="mb-4 self-center rounded-full border border-gold px-4 py-1 text-sm font-semibold text-gold">
        {RESULT_LABELS[resultType]}
      </div>
      <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
        {RESULT_TEXTS[resultType]}
      </div>
      <button
        onClick={onNext}
        className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
      >
        {RESULT_NEXT_BUTTON_LABEL}
      </button>
    </div>
  );
}
