import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { routes } from "../app/routes";
import { canonicalLicense, licenseContents } from "../legal/license";
import { ThemeProvider } from "../theme/ThemeProvider";

const normalize = (text: string) => text.replace(/\s+/g, " ").trim();
function mount(path = "/license") {
  return render(<ThemeProvider><RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} /></ThemeProvider>);
}

describe("public license page", () => {
  it("renders without a session or API request, with identity and the entire canonical license", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const view = mount();
    expect(screen.getByRole("heading", { level: 1, name: "GNU General Public License" })).toBeVisible();
    expect(screen.getByText("Copyright © 2026 akiamuradev")).toBeVisible();
    expect(screen.getAllByText(/GPL-3.0-or-later/).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: /GNU GENERAL PUBLIC LICENSE.*Version 3, 29 June 2007/ })).toBeVisible();
    const legalBody = view.container.querySelector(".license-document__body");
    expect(normalize(legalBody?.textContent ?? "")).toBe(normalize(canonicalLicense));
    expect(legalBody?.querySelector("pre")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "Скачать исходный текст LICENCE" })).toHaveAttribute("href", "/LICENCE.txt");
  });

  it("provides all 20 stable section anchors, source and third-party references", () => {
    mount();
    fireEvent.click(screen.getByText("Оглавление", { selector: "summary" }));
    const nav = screen.getByRole("navigation", { name: "Оглавление лицензии" });
    expect(licenseContents).toHaveLength(20);
    expect(within(nav).getAllByRole("link")).toHaveLength(20);
    for (const block of licenseContents) {
      expect(within(nav).getByRole("link", { name: block.title })).toHaveAttribute("href", `#${block.id ?? ""}`);
      expect(document.getElementById(block.id ?? "")).toHaveTextContent(block.title);
    }
    expect(document.getElementById("gpl-section-17")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Исходный код" })).toHaveAttribute("href", "https://github.com/akiamuradev/arduino-component-knowledge-base");
    for (const path of ["THIRD_PARTY_NOTICES.md", "docs/DATA_LICENSING.md"]) {
      expect(screen.getByRole("link", { name: path })).toHaveAttribute("href", `https://github.com/akiamuradev/arduino-component-knowledge-base/blob/main/${path}`);
    }
  });

  it("honors direct section anchors and supports the shared appearance preferences", async () => {
    localStorage.setItem("ackb-ui-preferences", JSON.stringify({ version: 2, theme: "dark", accent: { type: "custom", value: "#B45CFF" }, savedAccents: [] }));
    mount("/license#gpl-section-15");
    expect(document.getElementById("gpl-section-15")).toHaveFocus();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.style.getPropertyValue("--color-accent")).toBe("#B45CFF");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Настройки сайта" }));
    await user.click(screen.getByRole("radio", { name: "Orange" }));
    expect(document.documentElement.style.getPropertyValue("--color-accent")).toBe("#FF9D3D");
  });
});
