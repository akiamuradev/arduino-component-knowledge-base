import { type ClipboardEvent, type KeyboardEvent, useRef } from "react";

import type { TechnicalSpecificationInput } from "../api/contracts";
import {
  duplicateSpecificationKeys,
  insertPastedSpecifications,
  isEmptySpecification,
  MAX_SPECIFICATIONS,
  parseSpecificationPaste,
  specificationError,
  specificationKey,
  withTrailingSpecification,
} from "../editor/technical-specifications";

interface Props {
  items: TechnicalSpecificationInput[];
  onChange: (items: TechnicalSpecificationInput[]) => void;
}

export function TechnicalSpecificationsEditor({ items, onChange }: Props) {
  const labelInputs = useRef<(HTMLInputElement | null)[]>([]);
  const duplicates = duplicateSpecificationKeys(items);
  const actualCount = items.filter((item) => !isEmptySpecification(item)).length;

  const update = (index: number, field: "label" | "value_text", value: string) => {
    onChange(withTrailingSpecification(items.map((item, position) =>
      position === index ? { ...item, [field]: value } : item)));
  };
  const remove = (index: number) => {
    onChange(withTrailingSpecification(items.filter((_, position) => position !== index)));
  };
  const paste = (event: ClipboardEvent<HTMLInputElement>, index: number) => {
    const parsed = parseSpecificationPaste(event.clipboardData.getData("text/plain"));
    if (parsed.length === 0) return;
    event.preventDefault();
    const next = insertPastedSpecifications(items, index, parsed);
    onChange(next);
    const nextIndex = Math.min(
      next.length - 1,
      items.slice(0, index).filter((item) => !isEmptySpecification(item)).length
        + Math.min(parsed.length, MAX_SPECIFICATIONS - actualCount),
    );
    requestAnimationFrame(() => labelInputs.current[nextIndex]?.focus());
  };
  const moveToNextRow = (event: KeyboardEvent<HTMLInputElement>, index: number) => {
    if (event.key !== "Enter" || event.nativeEvent.isComposing) return;
    event.preventDefault();
    if (specificationError(items[index] ?? emptyRow) !== null) return;
    labelInputs.current[index + 1]?.focus();
  };

  return (
    <div className="specification-editor">
      <table aria-label="Технические характеристики">
        <thead><tr><th scope="col">Характеристика</th><th scope="col">Значение</th><th className="specification-editor__delete-heading" scope="col"><span className="sr-only">Действия</span></th></tr></thead>
        <tbody>{items.map((item, index) => {
          const error = specificationError(item);
          const generatedKey = item.key.trim() || specificationKey(item.label);
          const duplicate = !isEmptySpecification(item) && duplicates.has(generatedKey);
          const message = error ?? (duplicate ? "Такая характеристика уже добавлена." : null);
          const errorId = `specification-error-${String(index)}`;
          return <tr className={message === null ? undefined : "specification-editor__row--invalid"} key={`${item.key}:${String(index)}`}>
            <td data-label="Характеристика">
              <label className="sr-only" htmlFor={`specification-label-${String(index)}`}>Характеристика {String(index + 1)}</label>
              <input
                aria-describedby={message === null ? undefined : errorId}
                aria-invalid={message === null ? undefined : true}
                id={`specification-label-${String(index)}`}
                maxLength={160}
                onChange={(event) => { update(index, "label", event.target.value); }}
                onPaste={(event) => { paste(event, index); }}
                placeholder="Например, напряжение питания"
                ref={(element) => { labelInputs.current[index] = element; }}
                value={item.label}
              />
              {message === null ? null : <span className="specification-editor__error" id={errorId}>{message}</span>}
            </td>
            <td data-label="Значение">
              <label className="sr-only" htmlFor={`specification-value-${String(index)}`}>Значение характеристики {String(index + 1)}</label>
              <input
                aria-describedby={message === null ? undefined : errorId}
                aria-invalid={message === null ? undefined : true}
                id={`specification-value-${String(index)}`}
                maxLength={2000}
                onChange={(event) => { update(index, "value_text", event.target.value); }}
                onKeyDown={(event) => { moveToNextRow(event, index); }}
                onPaste={(event) => { paste(event, index); }}
                placeholder="Например, 5 В"
                value={item.value_text}
              />
            </td>
            <td className="specification-editor__delete-cell">
              {isEmptySpecification(item) ? null : <button aria-label={`Удалить характеристику ${String(index + 1)}`} className="button button--quiet" onClick={() => { remove(index); }} type="button">×</button>}
            </td>
          </tr>;
        })}</tbody>
      </table>
      <div className="specification-editor__footer">
        <span>{String(actualCount)} из {String(MAX_SPECIFICATIONS)}</span>
        <span>Можно вставить строки из таблицы, разделённые Tab.</span>
      </div>
    </div>
  );
}

const emptyRow: TechnicalSpecificationInput = {
  key: "", label: "", value_text: "", value_number: null, unit: null,
};
