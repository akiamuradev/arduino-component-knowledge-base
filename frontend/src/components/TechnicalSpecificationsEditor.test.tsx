import { render, screen, within } from "@testing-library/react";
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
  it("places server issues under their exact row and field with accessible descriptions", () => {
    const items = Array.from({ length: 8 }, (_, index) => ({ ...emptySpecification(), key: `p${String(index)}`, label: `Параметр ${String(index)}`, value_text: "4 мс" }));
    render(<TechnicalSpecificationsEditor items={items} onChange={() => undefined} issues={[
      { path: ["specifications", 7, "value_text"], code: "incompatible_unit", meta: { label: "Flash-память", entered_unit: "мс", expected_unit: "КБ" } },
      { path: ["specifications", 2, "label"], code: "specification_definition_conflict", meta: { label: "Параметр 2" } },
    ]} />);
    const value = screen.getByLabelText("Значение характеристики 8");
    expect(value).toHaveAttribute("aria-invalid", "true");
    expect(value).toHaveAttribute("aria-describedby", "specification-value-error-7");
    expect(value).toHaveAccessibleDescription(/«мс» нельзя использовать/u);
    const cell = value.parentElement;
    if (!cell) throw new Error("Missing value cell");
    expect(within(cell).getByText(/Ожидается единица «КБ»/u)).toBeVisible();
    expect(screen.getByLabelText("Характеристика 8")).not.toHaveAttribute("aria-invalid");
    expect(screen.getByLabelText("Характеристика 3")).toHaveAccessibleDescription(/не соответствует/u);
    expect(screen.getByLabelText("Значение характеристики 3")).not.toHaveAttribute("aria-invalid");
  });

  it("gives missing-value client validation precedence over a server issue", () => {
    render(<TechnicalSpecificationsEditor items={[{ ...emptySpecification(), label: "Flash", value_text: "" }]} onChange={() => undefined} issues={[
      { path: ["specifications", 0, "value_text"], code: "expected_numeric_value", meta: { label: "Flash" } },
    ]} />);
    expect(screen.getByLabelText("Значение характеристики 1")).toHaveAccessibleDescription("Укажите значение характеристики.");
    expect(screen.queryByText(/ожидается одно числовое/u)).not.toBeInTheDocument();
  });
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
