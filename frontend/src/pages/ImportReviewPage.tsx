import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import type {
  ImportEnrichmentCandidate,
  ImportRelationType,
  ImportReviewWorkspace,
} from "../api/contracts";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { SplatEmptyState } from "../components/SplatEmptyState";
import {
  useDraftConfirmation,
  useEnrichmentDecision,
  useEnrichmentRelation,
  useIdentitySelection,
  useImportReview,
  useImportReviews,
  useParserIssue,
  useSpecificationMapping,
} from "../imports/review-queries";

const relationTypes: ImportRelationType[] = [
  "exact_component",
  "main_integrated_circuit",
  "onboard_component",
  "connector",
  "functional_equivalent",
];

function object(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function objects(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(object) : [];
}

function text(value: unknown, fallback = "—"): string {
  return typeof value === "string" && value.trim() !== "" ? value : fallback;
}

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function Evidence({ values }: { values: Record<string, unknown>[] }) {
  if (values.length === 0) return <p className="muted">Evidence не сохранён.</p>;
  return (
    <ul className="evidence-list">
      {values.map((item, index) => (
        <li key={`${text(item.section, "source")}-${String(index)}`}>
          <strong>{text(item.section, "Источник")}</strong>
          <span>{text(item.locator ?? item.source_path ?? item.source)}</span>
          <small>{text(item.parser_version, "parser version unknown")}</small>
        </li>
      ))}
    </ul>
  );
}

function EnrichmentCard({
  candidate,
  workspace,
  reason,
}: {
  candidate: ImportEnrichmentCandidate;
  workspace: ImportReviewWorkspace;
  reason: string;
}) {
  const decide = useEnrichmentDecision(workspace.id);
  const relation = useEnrichmentRelation(workspace.id);
  const [selectedRelation, setSelectedRelation] = useState(candidate.relation_type);
  const symbol = candidate.symbol;
  const disabled = workspace.status === "confirmed" || reason.trim().length < 3;
  return (
    <article className="review-card">
      <header>
        <div>
          <p className="section-kicker">{candidate.provider}</p>
          <h4>{text(symbol.name ?? symbol.symbol_name, candidate.external_identity)}</h4>
        </div>
        <span className={`status-badge status-badge--${candidate.status}`}>
          {candidate.status} · {Math.round(candidate.confidence_basis_points / 10)}%
        </span>
      </header>
      <label>
        Relation
        <select
          disabled={workspace.status === "confirmed"}
          value={selectedRelation}
          onChange={(event) => { setSelectedRelation(event.target.value as ImportRelationType); }}
        >
          {relationTypes.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>
      <button
        className="button button--quiet"
        disabled={disabled || selectedRelation === candidate.relation_type || relation.isPending}
        type="button"
        onClick={() => {
          relation.mutate({
            enrichmentId: candidate.id,
            expectedRevision: workspace.revision,
            relationType: selectedRelation,
            reason,
          });
        }}
      >
        Сохранить relation
      </button>
      {candidate.review_reasons.length === 0 ? null : (
        <ul>{candidate.review_reasons.map((item) => <li key={item}>{item}</li>)}</ul>
      )}
      <details>
        <summary>Score breakdown и evidence</summary>
        <dl className="score-breakdown">
          {candidate.score_breakdown.map((item, index) => (
            <div key={`${text(item.rule_id, "rule")}-${String(index)}`}>
              <dt>{text(item.signal ?? item.rule_id, "signal")}</dt>
              <dd>
                {typeof item.weight_basis_points === "number"
                  ? String(item.weight_basis_points)
                  : "—"} · {text(item.reason)}
              </dd>
            </div>
          ))}
        </dl>
        <Evidence values={candidate.evidence} />
      </details>
      <div className="inline-actions">
        <button
          className="button button--success"
          disabled={disabled || decide.isPending}
          type="button"
          onClick={() => {
            decide.mutate({
              enrichmentId: candidate.id,
              expectedRevision: workspace.revision,
              decision: "accept",
              reason,
            });
          }}
        >
          Принять enrichment
        </button>
        <button
          className="button button--danger"
          disabled={disabled || decide.isPending}
          type="button"
          onClick={() => {
            decide.mutate({
              enrichmentId: candidate.id,
              expectedRevision: workspace.revision,
              decision: "reject",
              reason,
            });
          }}
        >
          Отклонить enrichment
        </button>
      </div>
      {decide.isError || relation.isError ? (
        <p className="form-error" role="alert">Решение устарело или не прошло проверку.</p>
      ) : null}
    </article>
  );
}

function ReviewWorkspace({ workspace }: { workspace: ImportReviewWorkspace }) {
  const [reason, setReason] = useState("");
  const [taxonomy, setTaxonomy] = useState<Record<string, string>>({});
  const [issueCode, setIssueCode] = useState("parser.review");
  const [issueNote, setIssueNote] = useState("");
  const identity = useIdentitySelection(workspace.id);
  const mapping = useSpecificationMapping(workspace.id);
  const parserIssue = useParserIssue(workspace.id);
  const confirmation = useDraftConfirmation(workspace.id);
  const title = text(object(workspace.draft.title).value, "Review draft");
  const qualityScore = Number(workspace.quality_report.overall_score_basis_points ?? 0);
  const qualityIssues = objects(workspace.quality_report.issues);
  const modulePins = objects(workspace.module_connection.pins);
  const moduleInstructions = objects(workspace.module_connection.instructions);
  const immutable = workspace.status === "confirmed";
  const reasonMissing = reason.trim().length < 3;
  return (
    <section className="import-review-page">
      <Link className="back-link" to="/admin/import-reviews">← К очереди review</Link>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Evidence-first review · revision {workspace.revision}</p>
          <h2>{title}</h2>
        </div>
        <span className={`status-badge status-badge--${workspace.status}`}>
          {workspace.status}
        </span>
      </div>
      <p className="lede">
        Confidence и evidence показываются отдельно от публичного текста. Решения не изменяют
        исходный snapshot.
      </p>

      <section className="review-overview">
        <article>
          <p className="section-kicker">Quality</p>
          <strong>{Math.round(qualityScore / 10)}%</strong>
          <span>{text(workspace.quality_report.route, "route unknown")}</span>
        </article>
        <article>
          <p className="section-kicker">Confidence полей</p>
          <dl>
            {Object.entries(workspace.field_confidence).map(([field, confidence]) => (
              <div key={field}><dt>{field}</dt><dd>{confidence}</dd></div>
            ))}
          </dl>
        </article>
        <article>
          <p className="section-kicker">Конфликты</p>
          <strong>{workspace.conflicts.length}</strong>
          <span>normalization conflicts</span>
        </article>
      </section>

      {qualityIssues.length === 0 ? null : (
        <section className="review-section warning-list">
          <h3>Quality issues</h3>
          <ul>
            {qualityIssues.map((item) => (
              <li key={text(item.code)}><code>{text(item.code)}</code> · {text(item.severity)}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="review-section">
        <h3>Identity candidates</h3>
        <div className="review-card-grid">
          {workspace.identity_candidates.map((candidate) => (
            <article className="review-card" key={candidate.id}>
              <header>
                <div><h4>{candidate.canonical_name}</h4><p>{candidate.component_kind}</p></div>
                <span>{candidate.confidence}</span>
              </header>
              <p>{candidate.selected_category ?? "Категория не выбрана"} · {candidate.resolution_status}</p>
              <details><summary>Evidence и score breakdown</summary><pre>{JSON.stringify(candidate.evidence, null, 2)}</pre></details>
              <button
                className="button button--primary"
                disabled={immutable || candidate.selected || reasonMissing || identity.isPending}
                type="button"
                onClick={() => {
                  identity.mutate({
                    identityCandidateId: candidate.id,
                    expectedRevision: workspace.revision,
                    reason,
                  });
                }}
              >
                {candidate.selected ? "Identity выбран" : "Выбрать identity"}
              </button>
            </article>
          ))}
        </div>
      </section>

      <section className="review-section">
        <h3>Несопоставленные характеристики</h3>
        {workspace.unmapped_specifications.length === 0 ? (
          <p className="muted">Все характеристики сопоставлены с taxonomy.</p>
        ) : workspace.unmapped_specifications.map((specification) => (
          <article className="review-card spec-review-card" key={specification.key}>
            <div>
              <strong>{specification.original_label}</strong>
              <p>{specification.original_value}</p>
              <small>{specification.reason}</small>
            </div>
            <label>
              Taxonomy
              <select
                disabled={immutable}
                value={taxonomy[specification.key] ?? specification.mapped_taxonomy_path ?? ""}
                onChange={(event) => {
                  setTaxonomy((current) => ({
                    ...current,
                    [specification.key]: event.target.value,
                  }));
                }}
              >
                <option value="">Выберите путь</option>
                {workspace.taxonomy_options.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>
            <button
              className="button button--primary"
              disabled={
                immutable
                || reasonMissing
                || mapping.isPending
                || (taxonomy[specification.key] ?? "") === ""
              }
              type="button"
              onClick={() => {
                mapping.mutate({
                  specificationKey: specification.key,
                  taxonomyPath: taxonomy[specification.key] ?? "",
                  expectedRevision: workspace.revision,
                  reason,
                });
              }}
            >
              Сопоставить spec
            </button>
            <Evidence values={specification.evidence} />
          </article>
        ))}
      </section>

      <section className="review-section">
        <h3>KiCad enrichment candidates</h3>
        <div className="review-card-grid">
          {workspace.enrichments.map((candidate) => (
            <EnrichmentCard
              candidate={candidate}
              key={candidate.id}
              reason={reason}
              workspace={workspace}
            />
          ))}
        </div>
      </section>

      <div className="review-levels">
        <section className="review-section">
          <p className="section-kicker">Уровень готового устройства</p>
          <h3>Подключение модуля</h3>
          {moduleInstructions.map((item, index) => (
            <p key={String(index)}>{text(item.body)}</p>
          ))}
          <dl className="pin-list">
            {modulePins.map((pin, index) => (
              <div key={`${text(pin.number ?? pin.name, "pin")}-${String(index)}`}>
                <dt>{text(pin.number ?? pin.name, "Pin")}</dt>
                <dd>{text(pin.function)}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section className="review-section">
          <p className="section-kicker">Внутренний уровень</p>
          <h3>Внутренние компоненты</h3>
          {workspace.internal_electronic_components.map((item, index) => (
            <article key={`${text(item.record_id)}-${String(index)}`}>
              <strong>{text(item.name)}</strong>
              <p>{text(item.relation_type)} · {text(item.status)}</p>
            </article>
          ))}
        </section>
        <section className="review-section">
          <p className="section-kicker">Схемный уровень</p>
          <h3>Symbol и footprint KiCad</h3>
          {workspace.kicad_symbols.map((symbol, index) => (
            <article key={`${text(symbol.record_id)}-${String(index)}`}>
              <strong>{text(symbol.library)}:{text(symbol.symbol_name)}</strong>
              <p>Footprints: {list(symbol.footprint_filters).join(", ") || "—"}</p>
              <details>
                <summary>Выводы символа KiCad — не pinout модуля</summary>
                <ul>{objects(symbol.pins).map((pin, pinIndex) => (
                  <li key={`${text(pin.number)}-${String(pinIndex)}`}>
                    {text(pin.number)}: {text(pin.name)} · {text(pin.electrical_type)}
                  </li>
                ))}</ul>
              </details>
            </article>
          ))}
        </section>
      </div>

      <section className="review-section">
        <h3>Provenance draft</h3>
        <Evidence values={workspace.provenance} />
      </section>

      <section className="review-section parser-issue-form">
        <h3>Пометить проблему парсера</h3>
        <label>Код<input maxLength={80} value={issueCode} onChange={(event) => { setIssueCode(event.target.value); }} /></label>
        <label>Описание<textarea maxLength={1000} rows={3} value={issueNote} onChange={(event) => { setIssueNote(event.target.value); }} /></label>
        <button
          className="button button--quiet"
          disabled={immutable || issueCode.length < 3 || issueNote.trim().length < 3 || parserIssue.isPending}
          type="button"
          onClick={() => {
            parserIssue.mutate({
              code: issueCode,
              note: issueNote,
              expectedRevision: workspace.revision,
            });
          }}
        >
          Сохранить parser issue
        </button>
        {workspace.parser_issues.map((item) => (
          <p key={text(item.code)}><code>{text(item.code)}</code> · {text(item.note)}</p>
        ))}
      </section>

      <section className="review-section">
        <h3>Audit trail</h3>
        {workspace.audit_trail.length === 0 ? <p className="muted">Решений пока нет.</p> : (
          <ol className="audit-list">
            {workspace.audit_trail.map((item) => (
              <li key={item.id}>
                <strong>r{item.review_revision} · {item.action}</strong>
                <span>{item.reason}</span>
                <small>{item.occurred_at}</small>
              </li>
            ))}
          </ol>
        )}
      </section>

      <label className="decision-reason">
        Основание следующего решения
        <textarea
          disabled={immutable}
          maxLength={1000}
          minLength={3}
          rows={4}
          value={reason}
          onChange={(event) => { setReason(event.target.value); }}
        />
      </label>
      {identity.isError || mapping.isError || parserIssue.isError || confirmation.isError ? (
        <p className="form-error" role="alert">
          Решение не сохранено. Обновите workspace: revision могла измениться.
        </p>
      ) : null}
      <div className="editor-actions">
        <button
          className="button button--success"
          disabled={immutable || reasonMissing || confirmation.isPending}
          type="button"
          onClick={() => {
            confirmation.mutate({ reason, expectedRevision: workspace.revision });
          }}
        >
          {immutable ? "Draft подтверждён" : "Подтвердить draft"}
        </button>
        <span className="validation-note">
          Подтверждение требует решений по enrichment и mapping всех unmapped specs.
        </span>
      </div>
    </section>
  );
}

export function ImportReviewPage() {
  const { reviewDraftId } = useParams();
  const listQuery = useImportReviews();
  const detailQuery = useImportReview(reviewDraftId);
  if (reviewDraftId !== undefined) {
    if (detailQuery.isPending) return <LoadingState label="Загружаем evidence…" />;
    if (detailQuery.isError) {
      return <ErrorState title="Import review недоступен" message="Draft не найден или доступ запрещён." onRetry={() => { void detailQuery.refetch(); }} />;
    }
    return <ReviewWorkspace workspace={detailQuery.data} />;
  }
  if (listQuery.isPending) return <LoadingState label="Загружаем очередь review…" />;
  if (listQuery.isError) {
    return <ErrorState title="Очередь import review недоступна" message="Backend не вернул review drafts." onRetry={() => { void listQuery.refetch(); }} />;
  }
  return (
    <section className="import-review-page">
      <p className="eyebrow">Только administrator</p>
      <h2>Evidence-first import review</h2>
      <p className="lede">Проверка identity, taxonomy и KiCad enrichment до подтверждения draft.</p>
      {listQuery.data.items.length === 0 ? (
        <SplatEmptyState icon="✓" title="Очередь review пуста" description="Новых evidence-first drafts пока нет." />
      ) : (
        <div className="duplicate-queue">
          {listQuery.data.items.map((item) => (
            <Link key={item.id} to={`/admin/import-reviews/${item.id}`}>
              <strong>{item.title}</strong>
              <span>
                {Math.round(item.quality_score_basis_points / 10)}% · {item.quality_route}
                {" · "}revision {item.revision}
              </span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
