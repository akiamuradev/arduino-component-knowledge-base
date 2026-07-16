import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import type {
  ComponentCard,
  DuplicateCandidate,
  DuplicateDecision,
} from "../api/contracts";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import {
  useDuplicateCandidate,
  useDuplicateCandidates,
  useDuplicateDecision,
} from "../duplicates/queries";

const selectableFields: { key: keyof ComponentCard; label: string }[] = [
  { key: "title", label: "Название" },
  { key: "aliases", label: "Альтернативные названия" },
  { key: "manufacturer", label: "Производитель" },
  { key: "model", label: "Модель" },
  { key: "primary_category_id", label: "Категория" },
  { key: "tags", label: "Теги" },
  { key: "summary", label: "Краткое описание" },
  { key: "description", label: "Описание" },
  { key: "purpose", label: "Назначение" },
  { key: "usage_notes", label: "Использование" },
  { key: "safety_notes", label: "Безопасность" },
  { key: "difficulty", label: "Сложность" },
  { key: "teacher_notes", label: "Заметки преподавателя" },
  { key: "specifications", label: "Характеристики" },
  { key: "compatibility", label: "Совместимость" },
  { key: "code_examples", label: "Учебные примеры" },
];

function display(value: unknown): string {
  if (value === null || value === "") return "—";
  if (Array.isArray(value)) {
    return value.length === 0
      ? "—"
      : value.map((item) => (typeof item === "object" ? JSON.stringify(item) : String(item))).join(", ");
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function ScoreBreakdown({ evidence }: { evidence: Record<string, unknown> }) {
  const signals = typeof evidence.signals === "object" && evidence.signals !== null
    ? evidence.signals as Record<string, unknown>
    : {};
  const penalties = typeof evidence.penalties === "object" && evidence.penalties !== null
    ? evidence.penalties as Record<string, unknown>
    : {};
  return (
    <section className="score-panel">
      <h3>Расшифровка оценки</h3>
      <dl>
        {Object.entries(signals).map(([name, value]) => (
          <div key={name}><dt>{name}</dt><dd>{Number(value).toFixed(4)}</dd></div>
        ))}
        {Object.entries(penalties).map(([name, value]) => (
          <div className="score-penalty" key={name}><dt>{name}</dt><dd>−{Number(value).toFixed(4)}</dd></div>
        ))}
      </dl>
      <p>Конфликтов характеристик: {typeof evidence.spec_conflict_count === "number" ? evidence.spec_conflict_count : 0}</p>
    </section>
  );
}

function ReviewPanel({ candidate }: { candidate: DuplicateCandidate }) {
  const navigate = useNavigate();
  const mutation = useDuplicateDecision(candidate.id);
  const [survivor, setSurvivor] = useState(candidate.left.id);
  const [fieldSources, setFieldSources] = useState<Record<string, string>>(
    Object.fromEntries(selectableFields.map(({ key }) => [key, candidate.left.id])),
  );
  const [reason, setReason] = useState("");

  function decide(decision: DuplicateDecision) {
    const combines = decision === "merge" || decision === "attach";
    mutation.mutate({
      decision,
      left_revision: candidate.left.revision,
      right_revision: candidate.right.revision,
      survivor_component_id: combines ? survivor : null,
      field_sources: decision === "merge" ? fieldSources : {},
      reason,
    }, {
      onSuccess: () => { void navigate("/admin/duplicates"); },
    });
  }

  return (
    <section>
      <Link className="back-link" to="/admin/duplicates">← К очереди</Link>
      <div className="section-heading duplicate-heading">
        <div><p className="eyebrow">Только administrator</p><h2>Проверка дубликата</h2></div>
        <strong className="duplicate-score">{Math.round(candidate.score * 100)}%</strong>
      </div>
      <p className="lede">Алгоритм {candidate.algorithm_version} предлагает кандидата, но решение принимает администратор.</p>
      <div className="duplicate-columns">
        {[candidate.left, candidate.right].map((card) => (
          <article className="duplicate-card" key={card.id}>
            <label className="survivor-choice">
              <input checked={survivor === card.id} name="survivor" onChange={() => { setSurvivor(card.id); }} type="radio" />
              Оставить эту карточку основной
            </label>
            <h3>{card.title}</h3>
            <p>{card.summary}</p>
            <small>{card.status} · revision {card.revision} · {card.slug}</small>
          </article>
        ))}
      </div>
      <ScoreBreakdown evidence={candidate.evidence} />
      <section className="conflict-table" aria-label="Совпадения и конфликты полей">
        <h3>Совпадения и конфликты</h3>
        {selectableFields.map(({ key, label }) => {
          const leftValue = display(candidate.left[key]);
          const rightValue = display(candidate.right[key]);
          return (
            <div className={leftValue === rightValue ? "field-match" : "field-conflict"} key={key}>
              <strong>{label}<small>{leftValue === rightValue ? "совпадает" : "конфликт"}</small></strong>
              <label><input checked={fieldSources[key] === candidate.left.id} name={key} onChange={() => { setFieldSources((current) => ({ ...current, [key]: candidate.left.id })); }} type="radio" />{leftValue}</label>
              <label><input checked={fieldSources[key] === candidate.right.id} name={key} onChange={() => { setFieldSources((current) => ({ ...current, [key]: candidate.right.id })); }} type="radio" />{rightValue}</label>
            </div>
          );
        })}
      </section>
      <label className="decision-reason">Основание решения<textarea maxLength={2000} minLength={3} onChange={(event) => { setReason(event.target.value); }} rows={4} value={reason} /></label>
      {mutation.isError ? <p className="form-error" role="alert">Решение не сохранено. Обновите кандидата: карточки могли измениться.</p> : null}
      <div className="decision-actions">
        <button className="button button--success" disabled={reason.trim().length < 3 || mutation.isPending} onClick={() => { decide("merge"); }} type="button">Объединить поля</button>
        <button className="button button--primary" disabled={reason.trim().length < 3 || mutation.isPending} onClick={() => { decide("attach"); }} type="button">Привязать источник</button>
        <button className="button button--quiet" disabled={reason.trim().length < 3 || mutation.isPending} onClick={() => { decide("create"); }} type="button">Оставить обе</button>
        <button className="button button--danger" disabled={reason.trim().length < 3 || mutation.isPending} onClick={() => { decide("reject"); }} type="button">Отклонить совпадение</button>
      </div>
    </section>
  );
}

export function DuplicateReviewPage() {
  const { candidateId } = useParams();
  const list = useDuplicateCandidates();
  const detail = useDuplicateCandidate(candidateId);
  const query = candidateId === undefined ? list : detail;
  if (query.isPending) return <LoadingState label="Загружаем кандидатов…" />;
  if (query.isError) return <ErrorState title="Проверка дубликатов недоступна" message="Backend не вернул подтверждённые данные." onRetry={() => { void query.refetch(); }} />;
  if (candidateId !== undefined && detail.data !== undefined) return <ReviewPanel candidate={detail.data} />;
  if (list.data === undefined) return null;
  return (
    <section>
      <p className="eyebrow">Только administrator</p><h2>Проверка дубликатов</h2>
      <p className="lede">Очередь отсортирована по score. Ни один кандидат не объединяется автоматически.</p>
      {list.data.items.length === 0 ? <p className="empty-panel">Открытых кандидатов нет.</p> : (
        <div className="duplicate-queue">
          {list.data.items.map((item) => (
            <Link key={item.id} to={`/admin/duplicates/${item.id}`}>
              <strong>{item.left.title} ↔ {item.right.title}</strong>
              <span>{Math.round(item.score * 100)}% · {item.kind} · {item.algorithm_version}</span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
