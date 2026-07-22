import { useEffect, useRef, useState } from "react";
import { api, type FunnelState } from "@/api/client";
import LegalNote from "@/components/LegalNote";
import {
  BACK_TO_OFFER_LABEL,
  BUY_BUTTON_LABEL,
  BUY_EMAIL_INVALID,
  BUY_EMAIL_LABEL,
  PRODUCT_DETAIL_TEXTS,
} from "@/content/texts";
import { openLink } from "@/lib/telegram";

// То же правило, что services/validation.py::is_valid_email на бэке —
// клиентская проверка лишь экономит запрос, сервер валидирует повторно (422).
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

type Product = "book" | "practicum";

interface Props {
  product: Product;
  price: number;
  onPaymentSettled: (state: FunnelState) => void;
  onBack: () => void;
}

const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 120000;

export default function ProductDetail({ product, price, onPaymentSettled, onBack }: Props) {
  const [waiting, setWaiting] = useState(false);
  const [buying, setBuying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [emailInvalid, setEmailInvalid] = useState(false);

  // Guards against the auto-poll effect and handleManualCheck both detecting
  // settlement and firing onPaymentSettled for the same purchase.
  const settledRef = useRef(false);

  // Keeps the polling effect's dependency array free of onPaymentSettled, so
  // an unmemoized callback identity from the parent can't reset the deadline.
  const onPaymentSettledRef = useRef(onPaymentSettled);
  useEffect(() => {
    onPaymentSettledRef.current = onPaymentSettled;
  }, [onPaymentSettled]);

  useEffect(() => {
    if (!waiting) return;

    settledRef.current = false;
    const deadline = Date.now() + POLL_TIMEOUT_MS;

    async function check() {
      let state: FunnelState;
      try {
        state = await api.getFunnelState();
      } catch {
        return;
      }
      if (settledRef.current) return;
      if (state.checkpoint !== `${product}_viewed`) {
        settledRef.current = true;
        clearInterval(interval);
        onPaymentSettledRef.current(state);
      }
    }

    function onVisible() {
      if (document.visibilityState === "visible") check();
    }

    const interval = setInterval(() => {
      if (Date.now() > deadline) {
        clearInterval(interval);
        return;
      }
      check();
    }, POLL_INTERVAL_MS);
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      settledRef.current = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [waiting, product]);

  async function handleBuy() {
    if (buying) return;
    const trimmed = email.trim();
    if (!EMAIL_RE.test(trimmed)) {
      setEmailInvalid(true);
      return;
    }
    setEmailInvalid(false);
    setBuying(true);
    setError(null);
    try {
      const { confirmation_url } = await api.buyProduct(product, trimmed);
      openLink(confirmation_url);
      setWaiting(true);
    } catch {
      setError("Не получилось открыть оплату. Попробуй ещё раз.");
    } finally {
      setBuying(false);
    }
  }

  async function handleManualCheck() {
    if (settledRef.current) return;
    let state: FunnelState;
    try {
      state = await api.getFunnelState();
    } catch {
      return;
    }
    if (settledRef.current) return;
    if (state.checkpoint !== `${product}_viewed`) {
      settledRef.current = true;
      onPaymentSettledRef.current(state);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-navy p-6 text-white">
      <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
        {PRODUCT_DETAIL_TEXTS[product]}
      </div>
      {error !== null && <p className="mt-2 text-sm text-red-400">{error}</p>}
      {waiting ? (
        <div className="mt-6 flex flex-col items-center gap-2">
          <p className="text-sm text-white/70">Проверяем оплату…</p>
          <button onClick={handleManualCheck} className="text-sm text-gold underline">
            Проверить оплату
          </button>
        </div>
      ) : (
        <>
          <p className="mt-6 text-sm text-white/70">{BUY_EMAIL_LABEL}</p>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@example.com"
            className="mt-2 w-full rounded-lg border border-gold/40 bg-white/5 px-4 py-3 text-white placeholder:text-white/40"
          />
          {emailInvalid && <p className="mt-2 text-sm text-red-400">{BUY_EMAIL_INVALID}</p>}
          <button
            onClick={handleBuy}
            className="mt-4 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
          >
            {`${BUY_BUTTON_LABEL[product]} за ${price} ₽`}
          </button>
          <LegalNote kind="purchase" />
          {!buying && (
            <button onClick={onBack} className="mt-4 text-center text-sm text-gold/70 underline">
              {BACK_TO_OFFER_LABEL}
            </button>
          )}
        </>
      )}
    </div>
  );
}
