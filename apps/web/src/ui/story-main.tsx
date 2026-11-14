import "@fontsource/atkinson-hyperlegible-next/400.css";
import "@fontsource/atkinson-hyperlegible-next/700.css";
import "@fontsource/atkinson-hyperlegible-next/800.css";
import "../styles/tokens.css";
import "../styles/app.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Story } from "./Story";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Story />
  </StrictMode>,
);
