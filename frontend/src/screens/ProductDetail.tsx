import { useEffect, useRef, useState } from "react";
import { api, type FunnelState } from "@/api/client";
import { BACK_TO_OFFER_LABEL, BUY_BUTTON_LABEL, PRODUCT_DETAIL_TEXTS } from "@/content/texts";
import { openLink } from "@/lib/telegram";

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
    setBuying(true);
    setError(null);
    try {
      const { confirmation_url } = await api.buyProduct(product);
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
          <button
            onClick={handleBuy}
            className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
          >
            {`${BUY_BUTTON_LABEL[product]} за ${price} ₽`}
          </button>
          <button onClick={onBack} className="mt-4 text-center text-sm text-gold/70 underline">
            {BACK_TO_OFFER_LABEL}
          </button>
        </>
      )}
    </div>
  );
}
