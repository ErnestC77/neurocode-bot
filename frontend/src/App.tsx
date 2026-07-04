import { useEffect, useState } from "react";
import { Route, Routes, useNavigate } from "react-router-dom";
import { api, ApiError, type FunnelState } from "./api/client";
import { resolveScreen } from "./funnel/resolveScreen";
import AdminPanel from "./screens/AdminPanel";
import Consent from "./screens/Consent";
import ConsultDetail from "./screens/ConsultDetail";
import ConsultEmailInput from "./screens/ConsultEmailInput";
import Offer from "./screens/Offer";
import ProductDetail from "./screens/ProductDetail";
import Quiz from "./screens/Quiz";
import Result from "./screens/Result";
import WelcomeCarousel from "./screens/WelcomeCarousel";

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Ошибка сети";
}

function FunnelApp() {
  const [state, setState] = useState<FunnelState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api
      .getFunnelState()
      .then(setState)
      .catch((err) => setError(errorMessage(err)));
  }, []);

  const screen = state ? resolveScreen(state.checkpoint, state.result_type) : null;

  useEffect(() => {
    if (screen) navigate(`/${screen}`, { replace: true });
  }, [screen, navigate]);

  if (error !== null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-navy p-6 text-white">
        <p className="text-red-400">Ошибка: {error}</p>
      </div>
    );
  }

  if (state === null || screen === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-navy p-6 text-white">
        <p>Загрузка…</p>
      </div>
    );
  }

  function runAction(action: () => Promise<FunnelState>) {
    action().then(setState).catch((err) => setError(errorMessage(err)));
  }

  switch (screen) {
    case "welcome":
      return <WelcomeCarousel onComplete={() => runAction(api.completeWelcome)} />;
    case "consent":
      return <Consent onAccept={() => runAction(api.acceptConsent)} />;
    case "quiz": {
      const questionNo = state.answers.length + 1;
      return <Quiz questionNo={questionNo} onAnswer={(score) => runAction(() => api.submitAnswer(questionNo, score))} />;
    }
    case "result":
      return <Result resultType={state.result_type!} onNext={() => runAction(api.showOffer)} />;
    case "offer":
      return (
        <Offer
          state={state}
          onRetake={() => runAction(api.retake)}
          onSelectProduct={(product) =>
            runAction(() =>
              product === "consult"
                ? api.viewConsult()
                : api.viewProduct(product as "book" | "practicum"),
            )
          }
        />
      );
    case "product-detail": {
      const product = state.checkpoint === "book_viewed" ? "book" : "practicum";
      const price = product === "book" ? state.book_price_rub : state.practicum_price_rub;
      return <ProductDetail product={product} price={price} onPaymentSettled={setState} />;
    }
    case "consult-detail":
      return <ConsultDetail onBook={() => runAction(api.bookConsult)} />;
    case "consult-email-input":
      return (
        <ConsultEmailInput
          onSubmit={api.submitConsultEmail}
          onDone={setState}
          onError={(msg) => setError(msg)}
        />
      );
  }
}

export default function App() {
  return (
    <Routes>
      <Route path="/admin" element={<AdminPanel />} />
      <Route path="*" element={<FunnelApp />} />
    </Routes>
  );
}
