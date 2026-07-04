import { getInitData } from "../lib/telegram";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...init?.headers,
      "X-Telegram-Init-Data": getInitData(),
    },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return response.json() as Promise<T>;
}

export interface AnswerOut {
  question_no: number;
  score: number;
}

export interface FunnelState {
  checkpoint: string;
  consent_given: boolean;
  result_type: string | null;
  answers: AnswerOut[];
  available_products: string[] | null;
  book_price_rub: number;
  practicum_price_rub: number;
}

export interface PurchaseInitiatedOut {
  confirmation_url: string;
}

export interface AdminLead {
  tg_id: number;
  username: string | null;
  email: string | null;
  worked_at: string | null;
  created_at: string;
}

export interface AdminPurchase {
  id: number;
  tg_id: number;
  username: string | null;
  product: string;
  amount_rub: number;
  status: string;
  paid_at: string | null;
  delivered_at: string | null;
}

export interface AdminUser {
  tg_id: number;
  username: string | null;
  first_name: string | null;
  checkpoint: string;
  result_type: string | null;
  test_attempt: number;
  created_at: string;
}

function postFunnel(path: string, body?: unknown): Promise<FunnelState> {
  return request<FunnelState>(`/api/funnel/${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
}

export const api = {
  ping: () => request<{ tg_id: number }>("/api/ping"),
  getFunnelState: () => request<FunnelState>("/api/funnel/state"),
  completeWelcome: () => postFunnel("welcome/complete"),
  acceptConsent: () => postFunnel("consent"),
  submitAnswer: (questionNo: number, score: number) =>
    postFunnel("answers", { question_no: questionNo, score }),
  showOffer: () => postFunnel("offer/show"),
  retake: () => postFunnel("retake"),
  viewProduct: (product: "book" | "practicum") => postFunnel(`product/${product}/view`),
  buyProduct: (product: "book" | "practicum") =>
    request<PurchaseInitiatedOut>(`/api/funnel/product/${product}/buy`, { method: "POST" }),
  bookConsult: () => postFunnel("consult/book"),
  viewConsult: () => postFunnel("consult/view"),
  submitConsultEmail: (email: string) =>
    request<FunnelState>("/api/funnel/consult/email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    }),
};

async function requestBlob(path: string): Promise<Blob> {
  const response = await fetch(path, {
    headers: { "X-Telegram-Init-Data": getInitData() },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return response.blob();
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export const adminApi = {
  getLeads: () => request<AdminLead[]>("/api/admin/leads"),
  toggleLeadWorked: (tgId: number) =>
    request<AdminLead>(`/api/admin/leads/${tgId}/worked`, { method: "POST" }),
  getPurchases: () => request<AdminPurchase[]>("/api/admin/purchases"),
  getUsers: () => request<AdminUser[]>("/api/admin/users"),
  exportLeads: async () => downloadBlob(await requestBlob("/api/admin/leads/export"), "leads.xlsx"),
  exportPurchases: async () =>
    downloadBlob(await requestBlob("/api/admin/purchases/export"), "purchases.xlsx"),
  exportUsers: async () => downloadBlob(await requestBlob("/api/admin/users/export"), "users.xlsx"),
};
