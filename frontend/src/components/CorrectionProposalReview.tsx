import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { CorrectionProposalStatus } from "../api/contracts";
import { userErrorMessage } from "../api/errors";
import { workspaceKeys } from "../workspace/queries";
import { ErrorState, LoadingState } from "./AsyncStates";
import { SplatEmptyState } from "./SplatEmptyState";

const STATUS_LABELS: Readonly<Record<CorrectionProposalStatus, string>> = {
  open: "Ожидает решения",
  applied: "Учтено",
  dismissed: "Отклонено",
};

export function CorrectionProposalReview({ componentId }: { componentId: string }) {
  const queryClient = useQueryClient();
  const proposals = useQuery({
    queryKey: workspaceKeys.correctionProposals(componentId),
    queryFn: () => api.listCorrectionProposals(componentId),
  });
  const resolve = useMutation({
    mutationFn: ({
      proposalId,
      decision,
    }: {
      proposalId: string;
      decision: "applied" | "dismissed";
    }) => api.resolveComponentCorrection(componentId, proposalId, decision),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: workspaceKeys.correctionProposals(componentId),
      });
    },
  });

  if (proposals.isPending) {
    return <LoadingState label="Загружаем предложения исправлений…" />;
  }
  if (proposals.isError) {
    return (
      <ErrorState
        message="Предложения доступны автору карточки и администратору."
        onRetry={() => void proposals.refetch()}
      />
    );
  }
  if (proposals.data.total === 0) {
    return (
      <SplatEmptyState
        description="Преподаватели ещё не присылали замечаний к этой карточке."
        icon={<span aria-hidden="true">✓</span>}
        title="Предложений пока нет"
      />
    );
  }

  return (
    <section className="correction-proposal-review" aria-label="Предложения исправлений">
      <header>
        <div>
          <p className="eyebrow">Обратная связь преподавателей</p>
          <h3>Предложения исправлений</h3>
        </div>
        <span>{proposals.data.total}</span>
      </header>
      {resolve.isError ? (
        <p className="management-message management-message--error" role="alert">
          {userErrorMessage(resolve.error, "Не удалось обработать предложение.")}
        </p>
      ) : null}
      <ol>
        {proposals.data.items.map((item) => (
          <li key={item.id}>
            <header>
              <strong>{item.author_display_name}</strong>
              <span className={`status-badge status-badge--${item.status}`}>
                {STATUS_LABELS[item.status]}
              </span>
            </header>
            <p className="preserve-lines">{item.message}</p>
            <footer>
              <time dateTime={item.created_at}>
                {new Intl.DateTimeFormat("ru-RU", {
                  dateStyle: "medium",
                  timeStyle: "short",
                }).format(new Date(item.created_at))}
              </time>
              {item.status === "open" ? (
                <div>
                  <button
                    className="button button--quiet"
                    disabled={resolve.isPending}
                    onClick={() => {
                      resolve.mutate({ proposalId: item.id, decision: "dismissed" });
                    }}
                    type="button"
                  >
                    Отклонить
                  </button>
                  <button
                    className="button button--success"
                    disabled={resolve.isPending}
                    onClick={() => {
                      resolve.mutate({ proposalId: item.id, decision: "applied" });
                    }}
                    type="button"
                  >
                    Отметить учтённым
                  </button>
                </div>
              ) : null}
            </footer>
          </li>
        ))}
      </ol>
    </section>
  );
}
