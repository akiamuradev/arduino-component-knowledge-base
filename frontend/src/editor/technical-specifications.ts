import type { TechnicalSpecificationInput } from "../api/contracts";

export const MAX_SPECIFICATIONS = 50;

const CYRILLIC_TRANSLITERATION: Readonly<Record<string, string>> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z",
  и: "i", й: "i", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r",
  с: "s", т: "t", у: "u", ф: "f", х: "kh", ц: "ts", ч: "ch", ш: "sh",
  щ: "shch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
};

export function emptySpecification(): TechnicalSpecificationInput {
  return { key: "", label: "", value_text: "", value_number: null, unit: null };
}

export function isEmptySpecification(item: TechnicalSpecificationInput): boolean {
  return item.label.trim() === "" && item.value_text.trim() === "";
}

export function withTrailingSpecification(
  items: readonly TechnicalSpecificationInput[],
): TechnicalSpecificationInput[] {
  const meaningful = items.filter((item) => !isEmptySpecification(item));
  return meaningful.length < MAX_SPECIFICATIONS
    ? [...meaningful, emptySpecification()]
    : meaningful.slice(0, MAX_SPECIFICATIONS);
}

function stableHash(value: string): string {
  let hash = 2_166_136_261;
  for (const character of value) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16_777_619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function specificationKey(label: string): string {
  const normalized = label.normalize("NFKD").toLocaleLowerCase("ru-RU").trim()
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[а-яё]/g, (character) => CYRILLIC_TRANSLITERATION[character] ?? "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (normalized === "") return `spec-${stableHash(label.normalize("NFKC").trim())}`;
  if (normalized.length <= 100) return normalized;
  return `${normalized.slice(0, 91).replace(/-+$/g, "")}-${stableHash(normalized)}`;
}

export interface NumericSpecificationMetadata {
  valueNumber: string;
  unit: string;
}

export function numericSpecificationMetadata(
  value: string,
): NumericSpecificationMetadata | null {
  const normalized = value.trim().replace(/\s+/g, " ");
  const match = /^([+-]?\d{1,16}(?:[.,]\d{1,8})?)\s+([^\s]{1,32})$/u.exec(normalized);
  if (match === null) return null;
  const valueNumber = match[1];
  const unit = match[2];
  if (valueNumber === undefined || unit === undefined || !/[\p{L}%°Ωµμ]/u.test(unit)) {
    return null;
  }
  return { valueNumber: valueNumber.replace(",", "."), unit };
}

export function normalizedSpecificationValue(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

function unchangedOriginal(
  item: TechnicalSpecificationInput,
  originals: readonly TechnicalSpecificationInput[],
): TechnicalSpecificationInput | undefined {
  return originals.find((original) =>
    item.key !== "" && original.key === item.key
    && original.label === item.label && original.value_text === item.value_text);
}

export function specificationInputs(
  items: readonly TechnicalSpecificationInput[],
  originals: readonly TechnicalSpecificationInput[] = [],
): TechnicalSpecificationInput[] {
  return items.filter((item) => !isEmptySpecification(item)).map((item) => {
    const label = item.label.trim();
    const valueText = normalizedSpecificationValue(item.value_text);
    const original = unchangedOriginal(item, originals);
    if (original !== undefined) {
      return {
        key: original.key,
        label,
        value_text: valueText,
        value_number: original.value_number,
        unit: original.unit,
      };
    }
    const numeric = numericSpecificationMetadata(valueText);
    return {
      key: item.key.trim() || specificationKey(label),
      label,
      value_text: valueText,
      value_number: numeric?.valueNumber ?? null,
      unit: numeric?.unit ?? null,
    };
  });
}

export function specificationError(
  item: TechnicalSpecificationInput,
): string | null {
  const hasLabel = item.label.trim() !== "";
  const hasValue = item.value_text.trim() !== "";
  if (hasLabel && !hasValue) return "Укажите значение характеристики.";
  if (!hasLabel && hasValue) return "Укажите название характеристики.";
  return null;
}

export function duplicateSpecificationKeys(
  items: readonly TechnicalSpecificationInput[],
): ReadonlySet<string> {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const item of specificationInputs(items)) {
    if (seen.has(item.key)) duplicates.add(item.key);
    seen.add(item.key);
  }
  return duplicates;
}

export interface PastedSpecification {
  label: string;
  value: string;
}

export function parseSpecificationPaste(text: string): PastedSpecification[] {
  const lines = text.split(/\r?\n/u).map((line) => line.trim()).filter(Boolean);
  if (lines.length === 0) return [];
  const parsed = lines.map((line): PastedSpecification | null => {
    const tab = /^([^\t]+)\t+(.+)$/u.exec(line);
    const colon = /^([^:]+):\s+(.+)$/u.exec(line);
    const dash = /^(.+?)\s+[–—-]\s+(.+)$/u.exec(line);
    const match = tab ?? colon ?? dash;
    if (match?.[1] === undefined || match[2] === undefined) return null;
    const label = match[1].trim();
    const value = match[2].trim();
    return label === "" || value === "" ? null : { label, value };
  });
  return parsed.every((item) => item !== null) ? parsed : [];
}

export function insertPastedSpecifications(
  items: readonly TechnicalSpecificationInput[],
  rowIndex: number,
  pasted: readonly PastedSpecification[],
): TechnicalSpecificationInput[] {
  const meaningful = items.filter((item) => !isEmptySpecification(item));
  const populatedBefore = items.slice(0, rowIndex).filter((item) => !isEmptySpecification(item)).length;
  const current = items[rowIndex];
  const insertAt = current === undefined || isEmptySpecification(current)
    ? populatedBefore
    : populatedBefore + 1;
  const capacity = Math.max(0, MAX_SPECIFICATIONS - meaningful.length);
  const additions = pasted.slice(0, capacity).map(({ label, value }) => ({
    ...emptySpecification(), label, value_text: value,
  }));
  meaningful.splice(insertAt, 0, ...additions);
  return withTrailingSpecification(meaningful);
}

export function specificationDisplayValue(
  item: Pick<TechnicalSpecificationInput, "value_text" | "unit">,
): string {
  const value = item.value_text.trim();
  // Display text is independent of canonical numeric metadata and its precision limits.
  if (/^[+-]?\d+(?:[.,]\d+)?\s*[\p{L}%°Ωµμ][^\s]*$/u.test(value)) return item.value_text;
  const unit = item.unit?.trim();
  if (unit === undefined || unit === "") return value;
  return value === unit || value.endsWith(` ${unit}`) ? value : `${value} ${unit}`;
}
