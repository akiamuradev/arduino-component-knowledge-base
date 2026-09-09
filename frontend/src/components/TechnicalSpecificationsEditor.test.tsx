import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import type { TechnicalSpecificationInput } from "../api/contracts";
import { emptySpecification, withTrailingSpecification } from "../editor/technical-specifications";
import { TechnicalSpecificationsEditor } from "./TechnicalSpecificationsEditor";

function Harness({ initial = [] }: { initial?: TechnicalSpecificationInput[] }) {
  const [items, setItems] = useState(() => withTrailingSpecification(initial));
  return <TechnicalSpecificationsEditor items={items} onChange={setItems} />;
}

describe("technical specifications editor", () => {
  it("adds through two visible fields, keeps a trailing row and deletes a populated row", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.queryByLabelText("Ключ")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Число/u)).not.toBeInTheDocument();
    expect(screen.getAllByRole("textbox")).toHaveLength(2);

    await user.type(screen.getByLabelText("Характеристика 1"), "Напряжение питания");
    expect(screen.getAllByRole("textbox")).toHaveLength(4);
    await user.type(screen.getByLabelText("Значение характеристики 1"), "5 В");
    expect(screen.getByText("1 из 50")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Удалить характеристику 1" }));
    expect(screen.getAllByRole("textbox")).toHaveLength(2);
    expect(screen.getByText("0 из 50")).toBeVisible();
  });

  it("shows inline validation for a half-filled row", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(screen.getByLabelText("Значение характеристики 1"), "ATmega328P");
    expect(screen.getByText("Укажите название характеристики.")).toBeVisible();
    expect(screen.getByLabelText("Характеристика 1")).toHaveAttribute("aria-invalid", "true");
  });

  it("bulk-pastes rows and leaves existing rows untouched", async () => {
    const user = userEvent.setup();
    render(<Harness initial={[{
      ...emptySpecification(), key: "existing", label: "Существующая", value_text: "Не менять",
    }]} />);
    await user.click(screen.getByLabelText("Характеристика 2"));
    await user.paste("Микроконтроллер\tATmega328P\nТактовая частота\t16 МГц");
    expect(screen.getByLabelText("Характеристика 1")).toHaveValue("Существующая");
    expect(screen.getByLabelText("Значение характеристики 1")).toHaveValue("Не менять");
    expect(screen.getByLabelText("Характеристика 2")).toHaveValue("Микроконтроллер");
    expect(screen.getByLabelText("Значение характеристики 3")).toHaveValue("16 МГц");
    expect(screen.getAllByRole("textbox")).toHaveLength(8);
  });

  it("moves from a completed value to the next characteristic with Enter", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(screen.getByLabelText("Характеристика 1"), "Архитектура");
    const value = screen.getByLabelText("Значение характеристики 1");
    await user.type(value, "8-bit AVR");
    await user.type(value, "{Enter}");
    expect(screen.getByLabelText("Характеристика 2")).toHaveFocus();
  });

  it("stops at 50 populated rows without exposing a 51st input row", () => {
    const full = Array.from({ length: 50 }, (_, index) => ({
      ...emptySpecification(),
      label: `Параметр ${String(index + 1)}`,
      value_text: String(index + 1),
    }));
    render(<Harness initial={full} />);
    expect(screen.getByText("50 из 50")).toBeVisible();
    expect(screen.getAllByRole("textbox")).toHaveLength(100);
    expect(screen.queryByLabelText("Характеристика 51")).not.toBeInTheDocument();
  });
});
