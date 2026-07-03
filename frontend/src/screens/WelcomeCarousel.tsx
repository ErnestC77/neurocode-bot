import { useState } from "react";
import { WELCOME_STEPS } from "@/content/texts";

interface Props {
  onComplete: () => void;
}

export default function WelcomeCarousel({ onComplete }: Props) {
  const [step, setStep] = useState(0);
  const current = WELCOME_STEPS[step];

  function handleNext() {
    if (step < WELCOME_STEPS.length - 1) {
      setStep(step + 1);
    } else {
      onComplete();
    }
  }

  return (
    <div className="flex min-h-screen flex-col justify-between bg-navy p-6 text-white">
      <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
        {current.text}
      </div>
      <button
        onClick={handleNext}
        className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
      >
        {current.buttonLabel}
      </button>
    </div>
  );
}
