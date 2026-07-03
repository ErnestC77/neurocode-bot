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
};
