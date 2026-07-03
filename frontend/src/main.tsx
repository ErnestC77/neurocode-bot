import "@telegram-apps/telegram-ui/dist/styles.css";
import { AppRoot } from "@telegram-apps/telegram-ui";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initTelegram } from "./lib/telegram";
import "./styles.css";

initTelegram();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppRoot appearance="dark" platform="base">
      <App />
    </AppRoot>
  </React.StrictMode>,
);
