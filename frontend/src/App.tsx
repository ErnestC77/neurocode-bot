import { useEffect, useState } from "react";
import { api, ApiError } from "./api/client";

export default function App() {
  const [tgId, setTgId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .ping()
      .then((res) => setTgId(res.tg_id))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка сети"));
  }, []);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-navy p-6 text-white">
      <h1 className="text-2xl font-bold text-gold">Диагностика нейрокода</h1>
      {tgId !== null && <p>Mini App подключён. Твой tg_id: {tgId}</p>}
      {error !== null && <p className="text-red-400">Ошибка: {error}</p>}
      {tgId === null && error === null && <p>Проверяю подключение…</p>}
    </div>
  );
}
