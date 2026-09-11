import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiRequest } from "../api/client";
import { hasPermission } from "../auth/permissions";
import { useCurrentUser } from "../auth/queries";

export function LegacyLicensePanel({ componentId }: { componentId: string }) {
  const user = useCurrentUser();
  const client = useQueryClient();
  const [evidence, setEvidence] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const key = ["legacy-provenance", componentId];
  const sources = useQuery({ queryKey: key, queryFn: () => apiRequest<{
    identity: string; source_name: string; license_status: string; license_evidence: string | null;
  }[]>(`/legacy-imports/components/${componentId}/provenance`) });
  const review = useMutation({ mutationFn: () => apiRequest(
    `/legacy-imports/components/${componentId}/license`, {
      method: "POST", csrf: true, body: JSON.stringify({ evidence, confirmation }),
    }), onSuccess: () => client.invalidateQueries({ queryKey: key }) });
  if (!sources.data?.length) return null;
  return <section className="license-panel">
    <h3>Права на материалы локального набора</h3>
    {sources.data.map((source) => <p key={source.identity}>
      {source.source_name}: {source.license_status === "reviewed" ? "проверены" : "неизвестны"}.
      {source.license_evidence}
    </p>)}
    {sources.data.some((source) => source.license_status !== "reviewed") && <p>
      Публикация заблокирована до проверки прав на текст и все изображения.
      Укажите лицензию или разрешение правообладателя и подтверждающий источник.</p>}
    {user.data && hasPermission(user.data, "imports.bulk_apply") && <>
      <label>Основание использования<textarea value={evidence} onChange={(e) => { setEvidence(e.target.value); }} /></label>
      <label>Введите ПРАВА ПРОВЕРЕНЫ<input value={confirmation} onChange={(e) => { setConfirmation(e.target.value); }} /></label>
      <button type="button" disabled={review.isPending || evidence.trim().length < 30 || confirmation !== "ПРАВА ПРОВЕРЕНЫ"}
        onClick={() => { review.mutate(); }}>Зафиксировать проверку прав</button>
      {review.error && <p role="alert">Не удалось сохранить проверку прав</p>}
    </>}
  </section>;
}
