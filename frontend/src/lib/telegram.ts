// Минимальная типизированная обёртка над Telegram WebApp JS SDK (грузится в
// index.html). Вне Telegram (например, обычный браузер при `npm run dev`)
// window.Telegram не определён — все хелперы деградируют, не роняя UI.

interface TelegramWebApp {
  initData: string;
  ready(): void;
  expand(): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebApp };
  }
}

export const tg: TelegramWebApp | undefined = window.Telegram?.WebApp;

export function initTelegram(): void {
  if (!tg) return;
  tg.ready();
  tg.expand();
}

export function getInitData(): string {
  return tg?.initData ?? "";
}
