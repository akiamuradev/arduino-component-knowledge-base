import { describe, expect, it } from "vitest";

import type { TechnicalSpecificationInput } from "../api/contracts";
import {
  emptySpecification,
  insertPastedSpecifications,
  MAX_SPECIFICATIONS,
  numericSpecificationMetadata,
  parseSpecificationPaste,
  specificationDisplayValue,
  specificationInputs,
  specificationKey,
  withTrailingSpecification,
} from "./technical-specifications";

function row(label: string, value: string): TechnicalSpecificationInput {
  return { ...emptySpecification(), label, value_text: value };
}

describe("technical specification mapping", () => {
  it("creates a stable backend key from an equivalent Cyrillic label", () => {
    expect(specificationKey("Напряжение питания")).toBe("napryazhenie-pitaniya");
    expect(specificationKey("  НАПРЯЖЕНИЕ   ПИТАНИЯ  ")).toBe("napryazhenie-pitaniya");
    expect(specificationKey("电压")).toMatch(/^spec-[0-9a-f]{8}$/u);
  });

  it.each([
    ["5 В", { valueNumber: "5", unit: "В" }],
    ["16 МГц", { valueNumber: "16", unit: "МГц" }],
    ["32 КБ", { valueNumber: "32", unit: "КБ" }],
    ["20 мА", { valueNumber: "20", unit: "мА" }],
    ["3,3 В", { valueNumber: "3.3", unit: "В" }],
  ])("extracts safe numeric metadata from %s", (value, expected) => {
    expect(numericSpecificationMetadata(value)).toEqual(expected);
  });

  it.each(["ATmega328P", "8-bit AVR", "I2C / SPI", "3.3–5 В", "5 В / 3.3 В"])(
    "does not guess metadata for textual or compound value %s",
    (value) => { expect(numericSpecificationMetadata(value)).toBeNull(); },
  );

  it("keeps display text and derives internal metadata for a new row", () => {
    expect(specificationInputs([row("Напряжение питания", "  5   В  ")])).toEqual([{
      key: "napryazhenie-pitaniya",
      label: "Напряжение питания",
      value_text: "5 В",
      value_number: "5",
      unit: "В",
    }]);
  });

  it("preserves the key and metadata of an untouched existing row", () => {
    const existing = {
      key: "clock-frequency", label: "Частота", value_text: "16",
      value_number: "16", unit: "МГц",
    } satisfies TechnicalSpecificationInput;
    expect(specificationInputs([existing, emptySpecification()], [existing])).toEqual([existing]);
  });

  it("ignores the empty trailing row and avoids displaying a unit twice", () => {
    expect(specificationInputs([row("Архитектура", "8-bit AVR"), emptySpecification()]))
      .toHaveLength(1);
    expect(specificationDisplayValue({ value_text: "5 В", unit: "В" })).toBe("5 В");
    expect(specificationDisplayValue({ value_text: "16", unit: "МГц" })).toBe("16 МГц");
  });

  it("parses tab, colon and spaced dash rows without parsing an ambiguous value", () => {
    expect(parseSpecificationPaste(
      "Микроконтроллер\tATmega328P\nАрхитектура: 8-bit AVR\nПитание - 5 В",
    )).toEqual([
      { label: "Микроконтроллер", value: "ATmega328P" },
      { label: "Архитектура", value: "8-bit AVR" },
      { label: "Питание", value: "5 В" },
    ]);
    expect(parseSpecificationPaste("8-bit AVR")).toEqual([]);
  });

  it("inserts pasted rows without overwriting populated rows", () => {
    const result = insertPastedSpecifications(
      withTrailingSpecification([row("Первая", "1"), row("Последняя", "3")]),
      0,
      [{ label: "Средняя", value: "2" }],
    );
    expect(result.map((item) => item.label)).toEqual(["Первая", "Средняя", "Последняя", ""]);
  });

  it("never creates more than 50 actual rows", () => {
    const full = Array.from({ length: MAX_SPECIFICATIONS }, (_, index) =>
      row(`Параметр ${String(index)}`, String(index)));
    const result = insertPastedSpecifications(
      full, full.length - 1, [{ label: "Лишняя", value: "51" }],
    );
    expect(result).toHaveLength(MAX_SPECIFICATIONS);
    expect(result.some((item) => item.label === "Лишняя")).toBe(false);
  });
});
