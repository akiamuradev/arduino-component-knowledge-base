import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type SyntheticEvent, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import type {
  Category,
  CodeExampleInput,
  CodeExampleVisibility,
  ComponentCompatibilityInput,
  ComponentCard,
  ComponentDraftInput,
  Difficulty,
  TechnicalSpecificationInput,
} from "../api/contracts";
import { api, ApiError } from "../api/client";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { LearningExample } from "../components/LearningExample";
import {
  workspaceCategoriesQuery,
  workspaceComponentQuery,
  workspaceKeys,
} from "../workspace/queries";

type EditorMode = "new" | "edit";
type EditorView = "edit" | "preview";

interface EditorState {
  slug: string;
  title: string;
  aliases: string;
  manufacturer: string;
  model: string;
  primaryCategoryId: string;
  tags: string;
  summary: string;
  description: string;
  purpose: string;
  usageNotes: string;
  safetyNotes: string;
  difficulty: Difficulty;
  teacherNotes: string;
  manualOriginal: boolean;
  specifications: TechnicalSpecificationInput[];
  compatibility: ComponentCompatibilityInput[];
  codeExamples: EditorCodeExample[];
}

interface EditorCodeExample extends Omit<CodeExampleInput, "libraries"> {
  libraries: string;
}

function emptyState(categories: Category[]): EditorState {
  return {
    slug: "",
    title: "",
    aliases: "",
    manufacturer: "",
    model: "",
    primaryCategoryId: categories[0]?.id ?? "",
    tags: "",
    summary: "",
    description: "",
    purpose: "",
    usageNotes: "",
    safetyNotes: "",
    difficulty: "beginner",
    teacherNotes: "",
    manualOriginal: true,
    specifications: [],
    compatibility: [],
    codeExamples: [],
  };
}

function stateFromCard(card: ComponentCard): EditorState {
  return {
    slug: card.slug,
    title: card.title,
    aliases: card.aliases.join(", "),
    manufacturer: card.manufacturer ?? "",
    model: card.model ?? "",
    primaryCategoryId: card.primary_category_id,
    tags: card.tags.join(", "),
    summary: card.summary,
    description: card.description,
    purpose: card.purpose ?? "",
    usageNotes: card.usage_notes ?? "",
    safetyNotes: card.safety_notes ?? "",
    difficulty: card.difficulty,
    teacherNotes: card.teacher_notes ?? "",
    manualOriginal: card.manual_original,
    specifications: card.specifications.map((item) => ({
      key: item.key,
      label: item.label,
      value_text: item.value_text,
      value_number: item.value_number,
      unit: item.unit,
    })),
    compatibility: card.compatibility.map((item) => ({
      target_type: item.target_type,
      name: item.name,
      version_constraint: item.version_constraint,
      notes: item.notes,
    })),
    codeExamples: card.code_examples.map((item) => ({
      title: item.title,
      language: item.language,
      practical_task: item.practical_task,
      hints: [...item.hints],
      body: item.body,
      libraries: item.libraries.join(", "),
      explanation: item.explanation,
      visibility: item.visibility,
    })),
  };
}

const nullable = (value: string): string | null => value.trim() || null;
const commaList = (value: string): string[] =>
  value.split(",").map((item) => item.trim()).filter(Boolean);

function toDraftInput(state: EditorState): ComponentDraftInput {
  return {
    slug: state.slug.trim(),
    title: state.title.trim(),
    aliases: commaList(state.aliases),
    manufacturer: nullable(state.manufacturer),
    model: nullable(state.model),
    primary_category_id: state.primaryCategoryId,
    tags: commaList(state.tags),
    summary: state.summary.trim(),
    description: state.description.trim(),
    purpose: nullable(state.purpose),
    usage_notes: nullable(state.usageNotes),
    safety_notes: nullable(state.safetyNotes),
    difficulty: state.difficulty,
    teacher_notes: nullable(state.teacherNotes),
    manual_original: state.manualOriginal,
    specifications: state.specifications.map((item) => ({
      key: item.key.trim(),
      label: item.label.trim(),
      value_text: item.value_text.trim(),
      value_number: nullable(item.value_number ?? ""),
      unit: nullable(item.unit ?? ""),
    })),
    compatibility: state.compatibility.map((item) => ({
      target_type: item.target_type,
      name: item.name.trim(),
      version_constraint: nullable(item.version_constraint ?? ""),
      notes: nullable(item.notes ?? ""),
    })),
    code_examples: state.codeExamples.map((item) => ({
      title: item.title.trim(),
      language: item.language.trim().toLowerCase(),
      practical_task: item.practical_task.trim(),
      hints: item.hints.map((hint) => hint.trim()),
      body: item.body,
      libraries: commaList(item.libraries),
      explanation: nullable(item.explanation ?? ""),
      visibility: item.visibility,
    })),
  };
}

function publicationProblems(state: EditorState): string[] {
  const problems: string[] = [];
  if (state.title.trim().length < 2) problems.push("название от 2 символов");
  if (state.summary.trim().length < 20) problems.push("аннотация от 20 символов");
  if (state.description.trim().length === 0) problems.push("описание");
  if (state.primaryCategoryId === "") problems.push("категория");
  return problems;
}

export function ComponentEditorPage({ mode }: { mode: EditorMode }) {
  const { componentId } = useParams();
  const categories = useQuery(workspaceCategoriesQuery);
  const component = useQuery({
    ...workspaceComponentQuery(componentId ?? ""),
    enabled: mode === "edit" && componentId !== undefined,
  });

  if (categories.isPending || (mode === "edit" && component.isPending)) {
    return <LoadingState label="Открываем редактор…" />;
  }
  if (categories.isError) {
    return <ErrorState message="Backend не вернул категории для редактора." onRetry={() => void categories.refetch()} />;
  }
  if (categories.data.length === 0) {
    return <ErrorState message="Нельзя создать карточку без категории." />;
  }
  if (mode === "edit" && (component.isError || component.data === undefined)) {
    return <ErrorState message="Не удалось загрузить актуальную revision карточки." onRetry={() => void component.refetch()} />;
  }

  const card = mode === "edit" ? component.data : undefined;
  return (
    <ComponentEditorForm
      key={`${card?.id ?? "new"}:${String(card?.revision ?? 0)}`}
      mode={mode}
      card={card}
      categories={categories.data}
      reloadServer={mode === "edit" ? () => void component.refetch() : undefined}
    />
  );
}

interface EditorFormProps {
  mode: EditorMode;
  card?: ComponentCard;
  categories: Category[];
  reloadServer?: () => void;
}

function ComponentEditorForm({ mode, card, categories, reloadServer }: EditorFormProps) {
  const [state, setState] = useState<EditorState>(() =>
    card === undefined ? emptyState(categories) : stateFromCard(card));
  const [view, setView] = useState<EditorView>("edit");
  const [archiveConfirmation, setArchiveConfirmation] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const acceptSaved = (saved: ComponentCard) => {
    queryClient.setQueryData(workspaceKeys.component(saved.id), saved);
    void queryClient.invalidateQueries({ queryKey: workspaceKeys.componentLists });
  };

  const save = useMutation({
    mutationFn: async () => {
      const input = toDraftInput(state);
      if (mode === "new") return api.createComponentDraft(input);
      if (card === undefined) throw new Error("Loaded component is required for editing");
      return api.updateComponentDraft(card.id, { ...input, revision: card.revision });
    },
    onSuccess: (saved) => {
      acceptSaved(saved);
      if (mode === "new") void navigate(`/admin/components/${saved.id}/edit`, { replace: true });
    },
  });

  const lifecycle = useMutation({
    mutationFn: async (action: "publish" | "archive") => {
      if (card === undefined) throw new Error("Save the draft before changing lifecycle");
      return action === "publish"
        ? api.publishComponent(card.id, card.revision)
        : api.archiveComponent(card.id, card.revision);
    },
    onSuccess: acceptSaved,
  });

  const conflict = [save.error, lifecycle.error].find(
    (error) => error instanceof ApiError && error.code === "revision_conflict",
  );
  const otherError = [save.error, lifecycle.error].find(
    (error) => error !== null && error !== conflict,
  );
  const problems = publicationProblems(state);
  const update = <K extends keyof EditorState>(key: K, value: EditorState[K]) => {
    setState((current) => ({ ...current, [key]: value }));
  };
  const updateSpecification = (
    index: number,
    key: keyof TechnicalSpecificationInput,
    value: string,
  ) => {
    update("specifications", state.specifications.map((item, position) =>
      position === index
        ? { ...item, [key]: key === "value_number" || key === "unit" ? value || null : value }
        : item));
  };
  const updateCompatibility = (
    index: number,
    key: keyof ComponentCompatibilityInput,
    value: string,
  ) => {
    update("compatibility", state.compatibility.map((item, position) =>
      position === index
        ? { ...item, [key]: key === "version_constraint" || key === "notes" ? value || null : value }
        : item));
  };
  const updateCodeExample = <K extends keyof EditorCodeExample>(
    index: number,
    key: K,
    value: EditorCodeExample[K],
  ) => {
    update("codeExamples", state.codeExamples.map((item, position) =>
      position === index ? { ...item, [key]: value } : item));
  };
  const submit = (event: SyntheticEvent<HTMLFormElement, SubmitEvent>) => {
    event.preventDefault();
    save.mutate();
  };

  return (
    <section>
      <div className="editor-header">
        <div>
          <p className="eyebrow">{mode === "new" ? "Новый draft" : `Revision ${String(card?.revision ?? 0)}`}</p>
          <h2>{state.title || "Без названия"}</h2>
        </div>
        <div className="editor-tabs" aria-label="Режим редактора">
          <button className={view === "edit" ? "active" : ""} type="button" onClick={() => { setView("edit"); }}>Редактор</button>
          <button className={view === "preview" ? "active" : ""} type="button" onClick={() => { setView("preview"); }}>Preview</button>
        </div>
      </div>

      {conflict === undefined ? null : (
        <div className="conflict-banner" role="alert">
          <div><strong>Карточку уже изменил другой пользователь</strong><p>Локальный текст сохранён в форме. Автоматическая перезапись остановлена.</p></div>
          {reloadServer === undefined ? null : <button className="button button--quiet" type="button" onClick={reloadServer}>Загрузить серверную revision</button>}
        </div>
      )}
      {otherError === undefined ? null : <div className="inline-error" role="alert">Операция не выполнена. Backend вернул ошибку; изменения остаются в редакторе.</div>}

      {view === "preview" ? (
        <ComponentPreview state={state} categories={categories} status={card?.status ?? "draft"} />
      ) : (
        <form className="editor-form" onSubmit={submit}>
          <fieldset><legend>Идентификация</legend><div className="form-grid">
            <EditorField label="Название" value={state.title} maxLength={160} required onChange={(value) => { update("title", value); }} />
            <EditorField label="Slug" value={state.slug} maxLength={160} required onChange={(value) => { update("slug", value); }} />
            <EditorField label="Производитель" value={state.manufacturer} maxLength={120} onChange={(value) => { update("manufacturer", value); }} />
            <EditorField label="Модель" value={state.model} maxLength={120} onChange={(value) => { update("model", value); }} />
            <label>Категория<select value={state.primaryCategoryId} onChange={(event) => { update("primaryCategoryId", event.target.value); }}>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
            <label>Сложность<select value={state.difficulty} onChange={(event) => { update("difficulty", event.target.value as Difficulty); }}><option value="beginner">Начальная</option><option value="intermediate">Средняя</option><option value="advanced">Продвинутая</option></select></label>
            <EditorField label="Альтернативные имена через запятую" value={state.aliases} onChange={(value) => { update("aliases", value); }} />
            <EditorField label="Теги через запятую" value={state.tags} onChange={(value) => { update("tags", value); }} />
          </div></fieldset>
          <fieldset><legend>Учебное содержание</legend>
            <EditorTextArea label="Аннотация" value={state.summary} maxLength={500} required onChange={(value) => { update("summary", value); }} />
            <EditorTextArea label="Описание (Markdown без raw HTML)" value={state.description} maxLength={30000} required rows={10} onChange={(value) => { update("description", value); }} />
            <EditorTextArea label="Назначение" value={state.purpose} maxLength={2000} onChange={(value) => { update("purpose", value); }} />
            <EditorTextArea label="Рекомендации" value={state.usageNotes} maxLength={5000} onChange={(value) => { update("usageNotes", value); }} />
            <EditorTextArea label="Безопасность" value={state.safetyNotes} maxLength={5000} onChange={(value) => { update("safetyNotes", value); }} />
            <EditorTextArea label="Заметки преподавателя — скрыты от student" value={state.teacherNotes} maxLength={10000} onChange={(value) => { update("teacherNotes", value); }} />
            <label className="checkbox"><input type="checkbox" checked={state.manualOriginal} onChange={(event) => { update("manualOriginal", event.target.checked); }} />Материал создан вручную</label>
          </fieldset>
          <fieldset><legend>Характеристики</legend><p className="field-help">Ключ стабилен между карточками; числовое значение используется будущими фильтрами.</p>
            <div className="structured-list">{state.specifications.map((item, index) => <div className="structured-row" key={`${item.key}:${String(index)}`}>
              <EditorField label="Ключ" value={item.key} maxLength={100} required onChange={(value) => { updateSpecification(index, "key", value); }} />
              <EditorField label="Название" value={item.label} maxLength={160} required onChange={(value) => { updateSpecification(index, "label", value); }} />
              <EditorField label="Отображаемое значение" value={item.value_text} maxLength={2000} required onChange={(value) => { updateSpecification(index, "value_text", value); }} />
              <EditorField label="Число (необязательно)" value={item.value_number ?? ""} maxLength={64} onChange={(value) => { updateSpecification(index, "value_number", value); }} />
              <EditorField label="Единица" value={item.unit ?? ""} maxLength={32} onChange={(value) => { updateSpecification(index, "unit", value); }} />
              <button className="button button--quiet" type="button" onClick={() => { update("specifications", state.specifications.filter((_, position) => position !== index)); }}>Удалить</button>
            </div>)}</div>
            <button className="button button--quiet" disabled={state.specifications.length >= 50} type="button" onClick={() => { update("specifications", [...state.specifications, { key: "", label: "", value_text: "", value_number: null, unit: null }]); }}>Добавить характеристику</button>
          </fieldset>
          <fieldset><legend>Совместимость</legend>
            <div className="structured-list">{state.compatibility.map((item, index) => <div className="structured-row" key={`${item.target_type}:${item.name}:${String(index)}`}>
              <label>Тип<select value={item.target_type} onChange={(event) => { updateCompatibility(index, "target_type", event.target.value); }}><option value="board">Плата</option><option value="library">Библиотека</option><option value="platform">Платформа</option></select></label>
              <EditorField label="Название" value={item.name} maxLength={160} required onChange={(value) => { updateCompatibility(index, "name", value); }} />
              <EditorField label="Версия" value={item.version_constraint ?? ""} maxLength={120} onChange={(value) => { updateCompatibility(index, "version_constraint", value); }} />
              <EditorField label="Примечание" value={item.notes ?? ""} maxLength={2000} onChange={(value) => { updateCompatibility(index, "notes", value); }} />
              <button className="button button--quiet" type="button" onClick={() => { update("compatibility", state.compatibility.filter((_, position) => position !== index)); }}>Удалить</button>
            </div>)}</div>
            <button className="button button--quiet" disabled={state.compatibility.length >= 30} type="button" onClick={() => { update("compatibility", [...state.compatibility, { target_type: "board", name: "", version_constraint: null, notes: null }]); }}>Добавить совместимость</button>
          </fieldset>
          <fieldset><legend>Учебные примеры кода</legend><p className="field-help">Код хранится и показывается только как текст: backend его не запускает.</p>
            <div className="structured-list">{state.codeExamples.map((item, index) => <section className="code-example-editor" key={`${String(index)}:${item.title}`}>
              <div className="form-grid">
                <EditorField label="Название задания" value={item.title} maxLength={160} required onChange={(value) => { updateCodeExample(index, "title", value); }} />
                <EditorField label="Язык (arduino, cpp, python)" value={item.language} maxLength={32} required onChange={(value) => { updateCodeExample(index, "language", value); }} />
                <EditorField label="Библиотеки через запятую" value={item.libraries} onChange={(value) => { updateCodeExample(index, "libraries", value); }} />
                <label>Видимость<select value={item.visibility} onChange={(event) => { updateCodeExample(index, "visibility", event.target.value as CodeExampleVisibility); }}><option value="student">Студент</option><option value="teacher">Только преподаватель</option></select></label>
              </div>
              <EditorTextArea label="Практическое задание" value={item.practical_task} maxLength={5000} required onChange={(value) => { updateCodeExample(index, "practical_task", value); }} />
              <div className="structured-list"><strong>Подсказки по порядку</strong>{item.hints.map((hint, hintIndex) => <div className="hint-editor" key={`${String(hintIndex)}:${hint}`}>
                <EditorTextArea label={`Подсказка ${String(hintIndex + 1)}`} value={hint} maxLength={2000} required rows={2} onChange={(value) => { updateCodeExample(index, "hints", item.hints.map((current, position) => position === hintIndex ? value : current)); }} />
                <button className="button button--quiet" type="button" onClick={() => { updateCodeExample(index, "hints", item.hints.filter((_, position) => position !== hintIndex)); }}>Удалить подсказку</button>
              </div>)}</div>
              <button className="button button--quiet" disabled={item.hints.length >= 10} type="button" onClick={() => { updateCodeExample(index, "hints", [...item.hints, ""]); }}>Добавить подсказку</button>
              <EditorTextArea label="Решение — скрыто до действия студента" value={item.body} maxLength={65536} required rows={10} onChange={(value) => { updateCodeExample(index, "body", value); }} />
              <EditorTextArea label="Объяснение решения" value={item.explanation ?? ""} maxLength={10000} onChange={(value) => { updateCodeExample(index, "explanation", value || null); }} />
              <button className="button button--danger" type="button" onClick={() => { update("codeExamples", state.codeExamples.filter((_, position) => position !== index)); }}>Удалить пример</button>
            </section>)}</div>
            <button className="button button--quiet" disabled={state.codeExamples.length >= 10} type="button" onClick={() => { update("codeExamples", [...state.codeExamples, { title: "", language: "arduino", practical_task: "", hints: [], body: "", libraries: "", explanation: null, visibility: "student" }]); }}>Добавить учебный пример</button>
          </fieldset>
          <div className="editor-actions">
            <button className="button button--primary" disabled={save.isPending || lifecycle.isPending} type="submit">{save.isPending ? "Сохраняем…" : "Сохранить draft"}</button>
            {card?.status === "draft" ? <button className="button button--success" disabled={problems.length > 0 || save.isPending || lifecycle.isPending} type="button" onClick={() => { lifecycle.mutate("publish"); }}>Опубликовать</button> : null}
            {card?.status === "published" && !archiveConfirmation ? <button className="button button--danger" type="button" onClick={() => { setArchiveConfirmation(true); }}>В архив</button> : null}
            {archiveConfirmation ? <><span>Архивировать опубликованную карточку?</span><button className="button button--danger" type="button" onClick={() => { lifecycle.mutate("archive"); }}>Подтвердить</button><button className="button button--quiet" type="button" onClick={() => { setArchiveConfirmation(false); }}>Отмена</button></> : null}
          </div>
          {card?.status === "draft" && problems.length > 0 ? <p className="validation-note">Для публикации заполните: {problems.join(", ")}.</p> : null}
        </form>
      )}
    </section>
  );
}

interface FieldProps { label: string; value: string; maxLength?: number; required?: boolean; onChange: (value: string) => void; }
function EditorField({ label, value, maxLength, required, onChange }: FieldProps) {
  return <label>{label}<input value={value} maxLength={maxLength} required={required} onChange={(event) => { onChange(event.target.value); }} /></label>;
}
function EditorTextArea({ label, value, maxLength, required, onChange, rows = 4 }: FieldProps & { rows?: number }) {
  return <label>{label}<textarea value={value} maxLength={maxLength} required={required} rows={rows} onChange={(event) => { onChange(event.target.value); }} /></label>;
}

function ComponentPreview({ state, categories, status }: { state: EditorState; categories: Category[]; status: string }) {
  const category = categories.find((item) => item.id === state.primaryCategoryId);
  return <article className="component-preview">
    <div className="preview-meta"><span className={`status-badge status-badge--${status}`}>{status}</span><span>{category?.name ?? "Без категории"}</span><span>{state.difficulty}</span></div>
    <p className="eyebrow">Предпросмотр карточки</p><h1>{state.title || "Без названия"}</h1>
    <p className="preview-summary">{state.summary || "Аннотация ещё не заполнена."}</p>
    <div className="preview-body"><section><h2>Описание</h2><p>{state.description || "Описание ещё не заполнено."}</p></section>
      {state.purpose ? <section><h2>Назначение</h2><p>{state.purpose}</p></section> : null}
      {state.specifications.length > 0 ? <section><h2>Характеристики</h2><dl className="specification-list">{state.specifications.map((item) => <div key={item.key}><dt>{item.label}</dt><dd>{item.value_text}{item.unit ? ` ${item.unit}` : ""}</dd></div>)}</dl></section> : null}
      {state.compatibility.length > 0 ? <section><h2>Совместимость</h2><ul className="compatibility-list">{state.compatibility.map((item, index) => <li key={`${item.target_type}:${item.name}:${String(index)}`}><strong>{item.name}</strong>{item.version_constraint ? <span>{item.version_constraint}</span> : null}{item.notes ? <p>{item.notes}</p> : null}</li>)}</ul></section> : null}
      {state.codeExamples.length > 0 ? <section><h2>Практика</h2>{state.codeExamples.map((item, position) => <LearningExample example={{ ...item, libraries: commaList(item.libraries), position }} key={`${String(position)}:${item.title}`} />)}</section> : null}
      {state.safetyNotes ? <section className="safety-callout"><h2>Безопасность</h2><p>{state.safetyNotes}</p></section> : null}
    </div>
    {commaList(state.tags).length > 0 ? <div className="tag-list">{commaList(state.tags).map((tag) => <span key={tag}>{tag}</span>)}</div> : null}
    <aside><strong>Заметки преподавателя</strong><p>{state.teacherNotes || "Нет заметок."}</p></aside>
  </article>;
}
