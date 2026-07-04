import { useEffect, useState } from "react";
import { adminApi, ApiError, type AdminLead, type AdminPurchase, type AdminUser } from "../api/client";
import { formatDateTime } from "../lib/utils";

type Tab = "leads" | "purchases" | "users";

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Ошибка сети";
}

const tabButtonClass = (active: boolean) =>
  `whitespace-nowrap rounded px-2 py-1 text-sm ${active ? "bg-white/10 font-bold" : ""}`;

const cellClass = "whitespace-nowrap px-2 py-1";

export default function AdminPanel() {
  const [tab, setTab] = useState<Tab>("leads");
  const [leads, setLeads] = useState<AdminLead[] | null>(null);
  const [purchases, setPurchases] = useState<AdminPurchase[] | null>(null);
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [leadsFilter, setLeadsFilter] = useState<"all" | "new" | "worked">("all");

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
    <div className="min-h-screen bg-navy p-3 text-white sm:p-4">
      <div className="mb-3 flex flex-wrap gap-2">
        <button onClick={() => setTab("leads")} className={tabButtonClass(tab === "leads")}>
          Лиды
        </button>
        <button onClick={() => setTab("purchases")} className={tabButtonClass(tab === "purchases")}>
          Покупки
        </button>
        <button onClick={() => setTab("users")} className={tabButtonClass(tab === "users")}>
          Пользователи
        </button>
      </div>

      {tab === "leads" && (
        <section>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <button
              onClick={() => adminApi.exportLeads().catch((err) => setError(errorMessage(err)))}
              className="whitespace-nowrap rounded bg-white/10 px-3 py-1 text-sm"
            >
              Экспорт в Excel
            </button>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => setLeadsFilter("all")} className={tabButtonClass(leadsFilter === "all")}>
                Все
              </button>
              <button onClick={() => setLeadsFilter("new")} className={tabButtonClass(leadsFilter === "new")}>
                Новые
              </button>
              <button
                onClick={() => setLeadsFilter("worked")}
                className={tabButtonClass(leadsFilter === "worked")}
              >
                Отработанные
              </button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="text-left text-sm">
              <thead>
                <tr>
                  <th className={cellClass}>Telegram ID</th>
                  <th className={cellClass}>Username</th>
                  <th className={cellClass}>Email</th>
                  <th className={cellClass}>Отработан</th>
                  <th className={cellClass}>Дата создания</th>
                </tr>
              </thead>
              <tbody>
                {leads
                  ?.filter((l) => {
                    if (leadsFilter === "new") return l.worked_at === null;
                    if (leadsFilter === "worked") return l.worked_at !== null;
                    return true;
                  })
                  .map((l) => (
                    <tr key={l.tg_id}>
                      <td className={cellClass}>{l.tg_id}</td>
                      <td className={cellClass}>{l.username ?? ""}</td>
                      <td className={cellClass}>{l.email ?? ""}</td>
                      <td className={cellClass}>
                        <input
                          type="checkbox"
                          checked={l.worked_at !== null}
                          onChange={() =>
                            adminApi
                              .toggleLeadWorked(l.tg_id)
                              .then((updated) =>
                                setLeads((prev) =>
                                  prev?.map((x) => (x.tg_id === updated.tg_id ? updated : x)) ?? prev,
                                ),
                              )
                              .catch((err) => setError(errorMessage(err)))
                          }
                        />
                      </td>
                      <td className={cellClass}>{formatDateTime(l.created_at)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {tab === "purchases" && (
        <section>
          <button
            onClick={() => adminApi.exportPurchases().catch((err) => setError(errorMessage(err)))}
            className="mb-2 whitespace-nowrap rounded bg-white/10 px-3 py-1 text-sm"
          >
            Экспорт в Excel
          </button>
          <div className="overflow-x-auto">
            <table className="text-left text-sm">
              <thead>
                <tr>
                  <th className={cellClass}>ID</th>
                  <th className={cellClass}>Telegram ID</th>
                  <th className={cellClass}>Username</th>
                  <th className={cellClass}>Продукт</th>
                  <th className={cellClass}>Сумма, ₽</th>
                  <th className={cellClass}>Статус</th>
                  <th className={cellClass}>Оплачено</th>
                  <th className={cellClass}>Доставлено</th>
                </tr>
              </thead>
              <tbody>
                {purchases?.map((p) => (
                  <tr key={p.id}>
                    <td className={cellClass}>{p.id}</td>
                    <td className={cellClass}>{p.tg_id}</td>
                    <td className={cellClass}>{p.username ?? ""}</td>
                    <td className={cellClass}>{p.product}</td>
                    <td className={cellClass}>{p.amount_rub}</td>
                    <td className={cellClass}>{p.status}</td>
                    <td className={cellClass}>{p.paid_at ? formatDateTime(p.paid_at) : ""}</td>
                    <td className={cellClass}>{p.delivered_at ? formatDateTime(p.delivered_at) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {tab === "users" && (
        <section>
          <button
            onClick={() => adminApi.exportUsers().catch((err) => setError(errorMessage(err)))}
            className="mb-2 whitespace-nowrap rounded bg-white/10 px-3 py-1 text-sm"
          >
            Экспорт в Excel
          </button>
          <div className="overflow-x-auto">
            <table className="text-left text-sm">
              <thead>
                <tr>
                  <th className={cellClass}>Telegram ID</th>
                  <th className={cellClass}>Username</th>
                  <th className={cellClass}>Имя</th>
                  <th className={cellClass}>Этап воронки</th>
                  <th className={cellClass}>Результат теста</th>
                  <th className={cellClass}>Попытка</th>
                  <th className={cellClass}>Дата регистрации</th>
                </tr>
              </thead>
              <tbody>
                {users?.map((u) => (
                  <tr key={u.tg_id}>
                    <td className={cellClass}>{u.tg_id}</td>
                    <td className={cellClass}>{u.username ?? ""}</td>
                    <td className={cellClass}>{u.first_name ?? ""}</td>
                    <td className={cellClass}>{u.checkpoint}</td>
                    <td className={cellClass}>{u.result_type ?? ""}</td>
                    <td className={cellClass}>{u.test_attempt}</td>
                    <td className={cellClass}>{formatDateTime(u.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
