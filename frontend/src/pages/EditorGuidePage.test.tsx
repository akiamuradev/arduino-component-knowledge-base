import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import guide from "../content/editorial-guide.md?raw";
import { EditorialMarkdown, EditorGuidePage } from "./EditorGuidePage";

describe("editorial guide", () => {
  it("renders the actual canonical guide with headings, lists, quotes and its specification table", () => {
    const { container } = render(<EditorGuidePage />);
    expect(screen.getByRole("heading", { level: 1, name: "Правила заполнения карточек" })).toBeVisible();
    expect(guide).toContain("# Руководство по заполнению карточек ACKB");
    expect(screen.getByRole("heading", { name: "Руководство по заполнению карточек ACKB" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Аннотация" })).toHaveAttribute("id", "guide-аннотация");
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Характеристика" })).toBeVisible();
    expect(within(table).getByRole("cell", { name: "2–400 cm" })).toBeVisible();
    expect(screen.getAllByRole("list").length).toBeGreaterThan(10);
    expect(container.querySelectorAll("blockquote").length).toBeGreaterThan(3);
    expect(container.querySelectorAll("hr").length).toBeGreaterThan(10);
    expect(screen.getByText("выбирайте второй вариант.")).toBeVisible();
    expect(screen.getByText("Последнее обновление: YYYY-MM-DD")).toBeVisible();
  });

  it("renders code and safe links, gives unique anchors and never executes raw HTML", () => {
    const { container } = render(<EditorialMarkdown>{[
      "## Повтор", "## Повтор", "[Источник](https://example.com/docs)",
      "[Опасная ссылка](javascript:alert(1))", "<script>alert(1)</script>",
      '<img src=x onerror="alert(1)">', "`inline code`", "```cpp\nvoid setup() {}\n```",
    ].join("\n\n")}</EditorialMarkdown>);
    expect(container.querySelector("script, img, [onerror]")).toBeNull();
    expect(screen.getByText("void setup() {}").closest("pre")).not.toBeNull();
    expect(screen.getByText("inline code").tagName).toBe("CODE");
    expect(screen.getByRole("link", { name: "Источник" })).toHaveAttribute("target", "_blank");
    expect(screen.getByRole("link", { name: "Источник" })).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText("Опасная ссылка")).not.toHaveAttribute("href", "javascript:alert(1)");
    expect(screen.getAllByRole("heading").map((heading) => heading.id)).toEqual(["guide-повтор", "guide-повтор-1"]);
  });
});
