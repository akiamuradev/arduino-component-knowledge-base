import { useMutation } from "@tanstack/react-query";
import { type SyntheticEvent, useState } from "react";

import { api } from "../api/client";
import { userErrorMessage } from "../api/errors";

export function CorrectionProposalForm({ componentId }: { componentId: string }) {
  const [message, setMessage] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const proposal = useMutation({
    mutationFn: () => api.proposeComponentCorrection(componentId, message.trim()),
    onSuccess: () => {
      setMessage("");
      setSubmitted(true);
    },
  });

  const submit = (event: SyntheticEvent<HTMLFormElement, SubmitEvent>) => {
    event.preventDefault();
    setSubmitted(false);
    proposal.mutate();
  };

  return (
    <section className="correction-proposal-form" aria-labelledby="correction-proposal-title">
      <div>
        <p className="section-kicker">Для преподавателя</p>
        <h2 id="correction-proposal-title">Нашли неточность?</h2>
        <p>
          Опишите, что следует проверить. Предложение попадёт редактору, но не изменит
          опубликованную карточку напрямую.
        </p>
      </div>
      <form onSubmit={submit}>
        <label htmlFor="correction-proposal-message">Предложение исправления</label>
        <textarea
          id="correction-proposal-message"
          maxLength={4000}
          minLength={10}
          onChange={(event) => {
            setMessage(event.target.value);
            setSubmitted(false);
          }}
          required
          rows={5}
          value={message}
        />
        <div className="correction-proposal-form__actions">
          <span>{message.length} / 4000</span>
          <button
            className="button button--primary"
            disabled={message.trim().length < 10 || proposal.isPending}
            type="submit"
          >
            {proposal.isPending ? "Отправляем…" : "Предложить исправление"}
          </button>
        </div>
        {submitted ? (
          <p className="management-message management-message--success" role="status">
            Предложение отправлено редактору.
          </p>
        ) : null}
        {proposal.isError ? (
          <p className="management-message management-message--error" role="alert">
            {userErrorMessage(
              proposal.error,
              "Не удалось отправить предложение. Попробуйте снова.",
            )}
          </p>
        ) : null}
      </form>
    </section>
  );
}
