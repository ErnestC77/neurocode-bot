import { QUESTIONS } from "@/content/texts";

interface Props {
  questionNo: number;
  onAnswer: (score: number) => void;
}

const OPTIONS: { label: string; score: number }[] = [
  { label: "Да", score: 2 },
  { label: "Иногда", score: 1 },
  { label: "Нет", score: 0 },
];

export default function Quiz({ questionNo, onAnswer }: Props) {
  const progressDeg = ((questionNo - 1) / 7) * 360;
  const ringStyle = {
    background: `conic-gradient(#e8c96a ${progressDeg}deg, rgba(255,255,255,0.15) ${progressDeg}deg 360deg)`,
  };

  return (
    <div className="flex min-h-screen flex-col items-center bg-navy p-6 text-white">
      <div className="mt-4 flex h-16 w-16 items-center justify-center rounded-full" style={ringStyle}>
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-navy text-xs font-bold text-gold">
          {questionNo}/7
        </div>
      </div>
      <div className="flex flex-1 items-center px-2 text-center text-lg font-semibold leading-snug">
        {QUESTIONS[questionNo]}
      </div>
      <div className="mb-4 flex w-full gap-2">
        {OPTIONS.map((option) => (
          <button
            key={option.label}
            onClick={() => onAnswer(option.score)}
            className="flex-1 rounded-full border border-gold/40 bg-gold/10 py-3 text-sm font-semibold text-gold"
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
