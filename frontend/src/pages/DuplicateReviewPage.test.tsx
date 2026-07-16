import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { ComponentCard, DuplicateCandidate, User } from "../api/contracts";
import { createQueryClient } from "../app/query-client";
import { routes } from "../app/routes";
import { currentUserQueryKey } from "../auth/queries";
import { duplicateKeys } from "../duplicates/queries";

const admin: User = {
  id: "00000000-0000-0000-0000-000000000001",
  login: "admin",
  display_name: "Администратор",
  roles: ["administrator"],
};

function card(id: string, title: string, model: string): ComponentCard {
  return {
    id,
    slug: title.toLowerCase().replaceAll(" ", "-"),
    status: "draft",
    title,
    aliases: [],
    manufacturer: "Arduino",
    model,
    primary_category: { id: "00000000-0000-0000-0000-000000000010", slug: "boards", name: "Платы" },
    primary_category_id: "00000000-0000-0000-0000-000000000010",
    tags: ["avr"],
    summary: `Учебная карточка ${title} для проверки дубликатов.`,
    description: `Описание ${title}`,
    purpose: null,
    usage_notes: null,
    safety_notes: null,
    difficulty: "beginner",
    teacher_notes: null,
    manual_original: false,
    published_at: null,
    revision: 2,
    updated_at: "2026-07-16T12:00:00Z",
    specifications: [],
    compatibility: [],
    code_examples: [],
  };
}

const candidate: DuplicateCandidate = {
  id: "00000000-0000-0000-0000-000000000020",
  kind: "fuzzy",
  status: "open",
  score: 0.82,
  algorithm_version: "fuzzy-v1",
  evidence: {
    signals: { title_trigram: 0.9, token_similarity: 0.8 },
    penalties: { model_conflict: 0.25 },
    spec_conflict_count: 1,
  },
  created_at: "2026-07-16T12:00:00Z",
  left: card("00000000-0000-0000-0000-000000000021", "Arduino Uno", "R3"),
  right: card("00000000-0000-0000-0000-000000000022", "Arduino Uno board", "R4"),
};

describe("duplicate review page", () => {
  it("shows both cards, evidence, conflicts and explicit decisions", async () => {
    const queryClient = createQueryClient();
    queryClient.setDefaultOptions({ queries: { retry: false, staleTime: Infinity } });
    queryClient.setQueryData(currentUserQueryKey, admin);
    queryClient.setQueryData(duplicateKeys.all, { items: [candidate], total: 1 });
    queryClient.setQueryData(duplicateKeys.detail(candidate.id), candidate);
    const router = createMemoryRouter(routes, {
      initialEntries: [`/admin/duplicates/${candidate.id}`],
    });
    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Проверка дубликата" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Arduino Uno" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Arduino Uno board" })).toBeVisible();
    expect(screen.getByText("model_conflict")).toBeVisible();
    expect(screen.getByText("R3")).toBeVisible();
    expect(screen.getByText("R4")).toBeVisible();
    expect(screen.getByRole("button", { name: "Объединить поля" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Привязать источник" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Оставить обе" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Отклонить совпадение" })).toBeDisabled();
  });
});
