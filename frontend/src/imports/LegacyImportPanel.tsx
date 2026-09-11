import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError, apiRequest } from "../api/client";

export const LEGACY_SOURCE = "Микроконтроллеры, модуля, компоненты и проекты";

interface Target {
  title: string;
  category: string;
  rows: number[];
  match: string;
  folder: string | null;
  description: string;
  specifications: { label: string; value: string; unit: string | null }[];
  images: { origin: string; path: string; sha256: string; purpose: string }[];
  candidates: { path: string; score: number }[];
  warnings: string[];
}

interface Item {
  id: string;
  target: Target;
  candidates: { id: string; title: string; score: number; status: string; merge_allowed: boolean }[];
  decision: string;
  status: string;
  result_id: string | null;
  warnings: string[];
  error_code: string | null;
}

interface Bundle {
  id: string;
  status: string;
  phase: string;
  plan_hash: string;
  statistics: Record<string, number>;
  items: Item[];
  error_code: string | null;
}

function upload(url: string, file: File, progress: (percent: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    // Signed URLs must remain on the application's HTTPS storage proxy.
    const target = new URL(url, window.location.origin);
    if (target.origin !== window.location.origin || !target.pathname.startsWith("/media-storage/")) {
      reject(new Error("Недопустимый адрес загрузки"));
      return;
    }
    request.open("PUT", target.toString());
    request.timeout = 15 * 60 * 1000;
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) progress(Math.round(event.loaded / event.total * 100));
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) resolve();
      else reject(new Error("Загрузка файла не завершена"));
    };
    request.onerror = request.ontimeout = () => { reject(new Error("Ошибка соединения при загрузке")); };
    request.send(file);
  });
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) return `Операция не выполнена: ${error.code}. Обновите план.`;
  return error instanceof Error ? error.message : "Не удалось выполнить операцию";
}

export function LegacyImportPanel() {
  const [params, setParams] = useSearchParams();
  const bundleId = params.get("legacy");
  const [zip, setZip] = useState<File | null>(null);
  const [xlsx, setXlsx] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [confirmation, setConfirmation] = useState("");
  const [filter, setFilter] = useState("");
  const client = useQueryClient();
  const bundles = useQuery({
    queryKey: ["legacy-bundles"],
    queryFn: () => apiRequest<{ id: string; status: string; created_at: string }[]>("/legacy-imports"),
  });
  const bundle = useQuery({
    queryKey: ["legacy-bundle", bundleId], enabled: bundleId !== null,
    queryFn: () => {
      if (!bundleId) throw new Error("Набор не выбран");
      return apiRequest<Bundle>(`/legacy-imports/${bundleId}`);
    },
    refetchInterval: (query) => ["analyzing", "applying"].includes(query.state.data?.status ?? "")
      ? 3000 : false,
  });
  async function refresh() {
    await client.invalidateQueries({ queryKey: ["legacy-bundle"] });
    await client.invalidateQueries({ queryKey: ["legacy-bundles"] });
  }
  const create = useMutation({
    mutationFn: async () => {
      if (!zip || !xlsx) throw new Error("Выберите оба исходных файла");
      if (zip.size > 200 * 1024 * 1024 || xlsx.size > 64 * 1024 * 1024) {
        throw new Error("Допустимо: ZIP до 200 МиБ, XLSX до 64 МиБ");
      }
      const created = await apiRequest<{ id: string; uploads: { zip: string; xlsx: string } }>(
        "/legacy-imports", { method: "POST", csrf: true,
          body: JSON.stringify({ zip_size: zip.size, xlsx_size: xlsx.size }) },
      );
      setParams({ legacy: created.id });
      await upload(created.uploads.zip, zip, (p) => { setProgress(Math.round(p * 0.8)); });
      await upload(created.uploads.xlsx, xlsx, (p) => { setProgress(80 + Math.round(p * 0.2)); });
      await apiRequest(`/legacy-imports/${created.id}/uploaded`, { method: "POST", csrf: true });
    },
    onSuccess: refresh,
  });
  const action = useMutation({
    mutationFn: ({ path, body, method = "POST" }: { path: string; body?: object; method?: string }) => {
      if (!bundleId) throw new Error("Набор не выбран");
      return apiRequest(`/legacy-imports/${bundleId}/${path}`, {
        method, csrf: true, body: body === undefined ? undefined : JSON.stringify(body),
      });
    },
    onSuccess: async () => { setConfirmation(""); await refresh(); },
  });
  const data = bundle.data;
  const busy = create.isPending || action.isPending;
  const unresolved = data?.items.filter((i) => i.decision === "review").length ?? 0;
  const error = create.error ?? action.error ?? bundle.error ?? bundles.error;
  return <section className="import-preview" aria-label="Импорт локального набора">
    <h3>{LEGACY_SOURCE}</h3>
    <p>Сначала загрузите ZIP и XLSX и выполните анализ. Анализ не меняет каталог.
      После проверки плана можно создать или дополнить только черновики.</p>
    <p>Имена участников из таблицы и папка «ПРОЕКТЫ» не импортируются.
      Лицензии требуют проверки перед публикацией.</p>
    <label>Ранее созданный набор
      <select value={bundleId ?? ""} onChange={(e) => { setParams(e.target.value ? { legacy: e.target.value } : {}); }}>
        <option value="">Новый набор</option>
        {bundles.data?.map((b) => <option key={b.id} value={b.id}>
          {new Date(b.created_at).toLocaleString("ru-RU")} · {b.status}
        </option>)}
      </select>
    </label>
    {!bundleId && <div className="form-grid">
      <label>Исходный ZIP (до 200 МиБ)<input type="file" accept=".zip"
        onChange={(e) => { setZip(e.target.files?.[0] ?? null); }} /></label>
      <label>Исходный XLSX (до 64 МиБ)<input type="file" accept=".xlsx"
        onChange={(e) => { setXlsx(e.target.files?.[0] ?? null); }} /></label>
      <button type="button" className="button button--primary" disabled={busy || !zip || !xlsx}
        onClick={() => { create.mutate(); }}>Загрузить исходники</button>
    </div>}
    {create.isPending && <label>Загрузка: {progress}% <progress max={100} value={progress} /></label>}
    {error && <p role="alert">{errorText(error)}</p>}
    {data && <>
      <p role="status">Состояние: {data.status}. {data.error_code}</p>
      <div className="inline-actions">
        {data.status === "uploaded" && <button type="button" disabled={busy}
          onClick={() => { action.mutate({ path: "analyze" }); }}>Анализировать ZIP + XLSX</button>}
        {(data.status === "failed" || (data.status === "completed" && data.items.some((i) => i.status === "failed"))) && <button type="button" disabled={busy}
          onClick={() => { action.mutate({ path: "retry" }); }}>Повторить незавершённую работу</button>}
        {!["completed", "cancelled"].includes(data.status) && <button type="button" disabled={busy}
          onClick={() => { action.mutate({ path: "cancel" }); }}>Отменить набор</button>}
      </div>
      {data.status === "uploading" && !create.isPending && <p>
        Если загрузка прервалась, отмените этот набор и создайте новый.</p>}
      {data.items.length > 0 && <>
        <dl className="source-facts">{Object.entries(data.statistics).map(([label, count]) =>
          <div key={label}><dt>{label}</dt><dd>{count}</dd></div>)}</dl>
        <p>План: <code>{data.plan_hash}</code>. Нерешённых позиций: {unresolved}.</p>
        <label>Фильтр позиций<input value={filter} placeholder="Название, категория, статус"
          onChange={(e) => { setFilter(e.target.value); }} /></label>
        {data.items.filter((i) => `${i.target.title} ${i.target.category} ${i.status} ${i.decision}`
          .toLocaleLowerCase().includes(filter.toLocaleLowerCase())).map((item) => <details key={item.id}>
          <summary>{item.target.title} · {item.decision} · {item.status}</summary>
          <p>{item.target.category} · строки Excel {item.target.rows.join(", ")}</p>
          <p>ZIP: {item.target.folder ?? "Папка не выбрана"} · {item.target.match}</p>
          {item.target.candidates.map((c) => <p key={c.path}>{c.score}% · {c.path}</p>)}
          <p>Описание: {item.target.description || "Нет — останется неполный черновик"}</p>
          <ul>{item.target.specifications.map((s, n) => <li key={n}>{s.label}: {s.value} {s.unit}</li>)}</ul>
          <p>Изображения: {item.target.images.length}</p>
          <ul>{item.target.images.map((i) => <li key={i.sha256}>{i.origin}: {i.path} · {i.purpose}</li>)}</ul>
          <p>Предупреждения: {[...new Set([...item.target.warnings, ...item.warnings])].join(", ")}</p>
          {item.error_code && <p role="alert">{item.error_code}</p>}
          {item.candidates.map((c) => <p key={c.id}>
            <Link to={`/admin/components/${c.id}/edit`}>{c.title}</Link> · {c.status} · {c.score}
            {data.status === "ready" && c.merge_allowed && <button type="button" disabled={busy}
              onClick={() => { action.mutate({ path: `items/${item.id}`, method: "PATCH",
                body: { plan_hash: data.plan_hash, decision: "merge", merge_id: c.id } }); }}>
              Дополнить этот черновик</button>}
          </p>)}
          {data.status === "ready" && <div className="inline-actions">
            <button type="button" disabled={busy} onClick={() => { action.mutate({
              path: `items/${item.id}`, method: "PATCH",
              body: { plan_hash: data.plan_hash, decision: "create" },
            }); }}>Создать отдельный черновик</button>
            <button type="button" disabled={busy} onClick={() => { action.mutate({
              path: `items/${item.id}`, method: "PATCH",
              body: { plan_hash: data.plan_hash, decision: "skip" },
            }); }}>Пропустить</button>
          </div>}
          {item.result_id && <Link to={`/admin/components/${item.result_id}/edit`}>Открыть карточку</Link>}
        </details>)}
        {data.status === "ready" && <div className="license-panel">
          <p>Неоднозначные папки не добавляются: отдельный черновик получит только данные,
            перечисленные в плане. Опубликованные карточки не меняются.</p>
          <label>Для применения введите ИМПОРТ<input value={confirmation}
            onChange={(e) => { setConfirmation(e.target.value); }} autoComplete="off" /></label>
          <button type="button" className="button button--primary"
            disabled={busy || confirmation !== "ИМПОРТ" || unresolved > 0}
            onClick={() => { action.mutate({ path: "apply", body: {
              plan_hash: data.plan_hash, confirmation,
            } }); }}>Применить проверенный план</button>
        </div>}
        {data.status === "completed" && <p>
          Применение плана завершено. Проверьте результаты каждой позиции и обработку медиа.
          Для позиций с изменившимися карточками нужен новый анализ. Публикация не выполнялась.</p>}
      </>}
    </>}
  </section>;
}
