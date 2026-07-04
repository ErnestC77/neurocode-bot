import { useEffect, useState } from "react";
import { adminApi, ApiError, type AdminLead, type AdminPurchase, type AdminUser } from "../api/client";
import { formatDateTime } from "../lib/utils";

type Tab = "leads" | "purchases" | "users";

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Ошибка сети";
}

export default function AdminPanel() {
  const [tab, setTab] = useState<Tab>("leads");
  const [leads, setLeads] = useState<AdminLead[] | null>(null);
  const [purchases, setPurchases] = useState<AdminPurchase[] | null>(null);
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminApi.getLeads().then(setLeads).catch((err) => setError(errorMessage(err)));
    adminApi.getPurchases().then(setPurchases).catch((err) => setError(errorMessage(err)));
    adminApi.getUsers().then(setUsers).catch((err) => setError(errorMessage(err)));
  }, []);

  if (error !== null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-navy p-6 text-white">
        <p className="text-red-400">Доступ запрещён или ошибка сети: {error}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-navy p-4 text-white">
      <div className="mb-4 flex gap-4">
        <button onClick={() => setTab("leads")} className={tab === "leads" ? "font-bold underline" : ""}>
          Лиды
        </button>
        <button onClick={() => setTab("purchases")} className={tab === "purchases" ? "font-bold underline" : ""}>
          Покупки
        </button>
        <button onClick={() => setTab("users")} className={tab === "users" ? "font-bold underline" : ""}>
          Пользователи
        </button>
      </div>

      {tab === "leads" && (
        <section>
          <button
            onClick={() => adminApi.exportLeads().catch((err) => setError(errorMessage(err)))}
            className="mb-2 rounded bg-white/10 px-3 py-1"
          >
            Экспорт в Excel
          </button>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th>Telegram ID</th>
                <th>Username</th>
                <th>Email</th>
                <th>Дата создания</th>
              </tr>
            </thead>
            <tbody>
              {leads?.map((l) => (
                <tr key={l.tg_id}>
                  <td>{l.tg_id}</td>
                  <td>{l.username ?? ""}</td>
                  <td>{l.email ?? ""}</td>
                  <td>{formatDateTime(l.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {tab === "purchases" && (
        <section>
          <button
            onClick={() => adminApi.exportPurchases().catch((err) => setError(errorMessage(err)))}
            className="mb-2 rounded bg-white/10 px-3 py-1"
          >
            Экспорт в Excel
          </button>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th>ID</th>
                <th>Telegram ID</th>
                <th>Username</th>
                <th>Продукт</th>
                <th>Сумма, ₽</th>
                <th>Статус</th>
                <th>Оплачено</th>
                <th>Доставлено</th>
              </tr>
            </thead>
            <tbody>
              {purchases?.map((p) => (
                <tr key={p.id}>
                  <td>{p.id}</td>
                  <td>{p.tg_id}</td>
                  <td>{p.username ?? ""}</td>
                  <td>{p.product}</td>
                  <td>{p.amount_rub}</td>
                  <td>{p.status}</td>
                  <td>{p.paid_at ? formatDateTime(p.paid_at) : ""}</td>
                  <td>{p.delivered_at ? formatDateTime(p.delivered_at) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {tab === "users" && (
        <section>
          <button
            onClick={() => adminApi.exportUsers().catch((err) => setError(errorMessage(err)))}
            className="mb-2 rounded bg-white/10 px-3 py-1"
          >
            Экспорт в Excel
          </button>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th>Telegram ID</th>
                <th>Username</th>
                <th>Имя</th>
                <th>Этап воронки</th>
                <th>Результат теста</th>
                <th>Попытка</th>
                <th>Дата регистрации</th>
              </tr>
            </thead>
            <tbody>
              {users?.map((u) => (
                <tr key={u.tg_id}>
                  <td>{u.tg_id}</td>
                  <td>{u.username ?? ""}</td>
                  <td>{u.first_name ?? ""}</td>
                  <td>{u.checkpoint}</td>
                  <td>{u.result_type ?? ""}</td>
                  <td>{u.test_attempt}</td>
                  <td>{formatDateTime(u.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
