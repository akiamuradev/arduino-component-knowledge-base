import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CatalogMedia, SourceSnapshot } from "../api/contracts";
import { MediaGallery } from "./MediaGallery";
import { SourceAttributionBlock } from "./SourceAttributionBlock";

const source: SourceSnapshot = {
  display_name: "Seeed Studio Wiki",
  original_url: "https://wiki.seeedstudio.com/Grove-Button/",
  repository_url: "https://github.com/Seeed-Studio/wiki-documents",
  license_name: "GNU General Public License v3.0 only",
  license_spdx: "GPL-3.0-only",
  license_url: "https://www.gnu.org/licenses/gpl-3.0.html",
  source_revision: "1234567890abcdef1234567890abcdef12345678",
  source_tag: "docusaurus-version",
  source_file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md",
  source_entry_name: null,
  modifications_notice: "Normalized into an educational component draft.",
  imported_at: "2026-07-15T10:00:00Z",
  attribution: "Based on Seeed Studio Wiki.",
  parser_name: "seeed_wiki",
  parser_version: "1.0.0",
};

describe("content presentation", () => {
  it("renders one and multiple real source attributions with safe external links", () => {
    const second: SourceSnapshot = { ...source, display_name: "Official KiCad Libraries", repository_url: "https://gitlab.com/kicad/libraries/kicad-symbols", original_url: "https://gitlab.com/kicad/libraries/kicad-symbols/-/blob/123/Sensor_Temperature.kicad_sym", license_name: "Creative Commons Attribution-ShareAlike 4.0", license_spdx: "CC-BY-SA-4.0", source_tag: "9.0.9.1", source_entry_name: "LM35", parser_name: "kicad_symbols" };
    const view = render(<SourceAttributionBlock sources={[source]} />);
    const link = screen.getByRole("link", { name: /Открыть источник/ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText(/Импортировано/)).toBeVisible();
    expect(screen.getByText(/docusaurus-version/)).toBeVisible();
    expect(screen.getByText(/GPL-3.0-only/)).toBeVisible();
    view.rerender(<SourceAttributionBlock sources={[source, second]} />);
    expect(screen.getByRole("heading", { name: "Источники материала" })).toBeVisible();
    expect(screen.getByText("Official KiCad Libraries")).toBeVisible();
    expect(screen.getByText(/CC-BY-SA-4.0/)).toBeVisible();
  });

  it("renders lazy images, native video and a deterministic fallback", () => {
    const items: CatalogMedia[] = [
      { id: "image", kind: "image", alt: "Датчик", thumbnailUrl: "/media/sensor.webp" },
      { id: "video", kind: "video", alt: "Демонстрация", processedUrl: "/media/demo.mp4", posterUrl: "/media/poster.webp" },
    ];
    render(<MediaGallery items={items} />);
    const image = screen.getByRole("img", { name: "Датчик" });
    expect(image).toHaveAttribute("loading", "lazy");
    const video = screen.getByLabelText("Демонстрация");
    expect(video).toHaveAttribute("controls");
    expect(video).not.toHaveAttribute("autoplay");
    fireEvent.error(image);
    expect(screen.getByRole("img", { name: "Датчик" })).toHaveTextContent("Медиа недоступно");
  });

  it("does not invent attribution for manual material", () => {
    const { container } = render(<SourceAttributionBlock sources={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
