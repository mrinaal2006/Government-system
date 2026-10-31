import "./styles/index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";

import { AppProviders, createQueryClient } from "./app/providers";
import { buildRoutes } from "./app/routes";

const router = createBrowserRouter(buildRoutes({ includeDevRoutes: import.meta.env.DEV }));
const queryClient = createQueryClient();

const root = document.getElementById("root");
if (!root) throw new Error("Root element #root not found");

createRoot(root).render(
  <StrictMode>
    <AppProviders client={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
);
