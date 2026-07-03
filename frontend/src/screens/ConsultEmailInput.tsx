import { useState } from "react";
import { ApiError, type FunnelState } from "@/api/client";
import {
  CONSULT_CONTINUE_BUTTON_LABEL,
  CONSULT_EMAIL_INVALID,
  CONSULT_EMAIL_PROMPT,
  M7_2_TEXT,
} from "@/content/texts";

interface Props {
  onSubmit: (email: string) => Promise<FunnelState>;
  onDone: (state: FunnelState) => void;
  onError: (message: string) => void;
}

export default function ConsultEmailInput({ onSubmit, onDone, onError }: Props) {
  const [email, setEmail] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [pendingState, setPendingState] = useState<FunnelState | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    if (submitting) return;
    setSubmitting(true);
    setInvalid(false);
    try {
      const state = await onSubmit(email);
      setPendingState(state);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setInvalid(true);
      } else {
        onError(err instanceof ApiError ? err.message : "Ошибка сети");
      }
    } finally {
      setSubmitting(false);
    }
  }

  // Не вызываем onDone сразу по успеху onSubmit — держим state локально, чтобы
  // сначала показать M7_2_TEXT (подтверждение записи), и уходим на следующий
  // экран только по явному тапу "Дальше".
  if (pendingState !== null) {
    return (
      <div className="flex min-h-screen flex-col justify-between bg-navy p-6 text-white">
        <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
          {M7_2_TEXT}
        </div>
        <button
          onClick={() => onDone(pendingState)}
          className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
        >
          {CONSULT_CONTINUE_BUTTON_LABEL}
        </button>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col justify-between bg-navy p-6 text-white">
      <div className="flex-1">
        <p className="whitespace-pre-line text-[15px] leading-relaxed">{CONSULT_EMAIL_PROMPT}</p>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="name@example.com"
          className="mt-4 w-full rounded-lg border border-gold/40 bg-white/5 px-4 py-3 text-white placeholder:text-white/40"
        />
        {invalid && <p className="mt-2 text-sm text-red-400">{CONSULT_EMAIL_INVALID}</p>}
      </div>
      <button
        onClick={handleSubmit}
        className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
      >
        Отправить
      </button>
    </div>
  );
}
