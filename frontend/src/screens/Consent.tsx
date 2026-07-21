import LegalNote from "@/components/LegalNote";
import { CONSENT_BUTTON_LABEL, CONSENT_TEXT } from "@/content/texts";

interface Props {
  onAccept: () => void;
}

export default function Consent({ onAccept }: Props) {
  return (
    <div className="flex min-h-screen flex-col justify-between bg-navy p-6 text-white">
      <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
        {CONSENT_TEXT}
      </div>
      <div>
        <button
          onClick={onAccept}
          className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
        >
          {CONSENT_BUTTON_LABEL}
        </button>
        <LegalNote kind="consent" />
      </div>
    </div>
  );
}
