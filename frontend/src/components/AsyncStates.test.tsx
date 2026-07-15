import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { ErrorState, LoadingState } from "./AsyncStates";

it("announces loading state", () => {
  render(<LoadingState label="Проверяем backend…" />);
  expect(screen.getByRole("status")).toHaveTextContent("Проверяем backend…");
});

it("announces an error and retries only on explicit action", async () => {
  const retry = vi.fn();
  render(<ErrorState message="Backend недоступен" onRetry={retry} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Backend недоступен");
  await userEvent.click(screen.getByRole("button", { name: "Повторить" }));
  expect(retry).toHaveBeenCalledOnce();
});
