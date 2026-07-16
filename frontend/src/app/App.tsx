import { QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { createQueryClient } from "./query-client";
import { routes } from "./routes";
import { ThemeProvider } from "../theme/ThemeProvider";

const queryClient = createQueryClient();
const router = createBrowserRouter(routes);

export function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
