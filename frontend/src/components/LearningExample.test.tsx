import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CodeExample } from "../api/contracts";
import { LearningExample } from "./LearningExample";

const example: CodeExample = {
  title: "Safe solution",
  language: "arduino",
  practical_task: "Complete the sketch.",
  hints: ["First hint", "Second hint"],
  body: '<img src=x onerror="alert(1)">\nvoid loop() {}',
  libraries: ["Arduino core"],
  explanation: "The source remains text.",
  visibility: "student",
  position: 0,
};

describe("learning example", () => {
  it("reveals ordered hints and escaped highlighted solution only on request", async () => {
    const user = userEvent.setup();
    const view = render(<LearningExample example={example} />);
    expect(view.container.querySelector(".learning-code")).not.toBeInTheDocument();
    expect(screen.queryByText("First hint")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Показать подсказку 1" }));
    expect(screen.getByText("First hint")).toBeVisible();
    expect(screen.queryByText("Second hint")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Показать подсказку 2" }));
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "First hint",
      "Second hint",
    ]);

    await user.click(screen.getByRole("button", { name: "Показать решение" }));
    expect(view.container.querySelector(".learning-code")).toHaveTextContent("<img src=x");
    expect(view.container.querySelector(".code-token--keyword")).toHaveTextContent("void");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    const writeText = vi.fn<(value: string) => Promise<void>>().mockResolvedValue();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    await user.click(screen.getByRole("button", { name: "Копировать" }));
    expect(writeText).toHaveBeenCalledWith(example.body);
    expect(screen.getByRole("button", { name: "Скопировано" })).toBeVisible();
  });
});
