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

  it("renders a primary-first keyboard gallery with captions and safe URL fallback", () => {
    const items: CatalogMedia[] = [
      {
        asset_id: "secondary",
        kind: "image",
        purpose: "detail",
        alt_text: "Разъёмы датчика",
        caption: "Крупный план",
        display_order: 0,
        is_primary: false,
        width: 800,
        height: 600,
        variants: [{
          name: "320w",
          mime: "image/webp",
          width: 320,
          height: 240,
          sha256: "1".repeat(64),
          url: "http://untrusted.invalid/secondary.webp",
        }],
      },
      {
        asset_id: "primary",
        kind: "image",
        purpose: "product",
        alt_text: "Датчик целиком",
        caption: "Основной вид",
        display_order: 1,
        is_primary: true,
        width: 1600,
        height: 1200,
        variants: [
          {
            name: "320w",
            mime: "image/webp",
            width: 320,
            height: 240,
            sha256: "2".repeat(64),
            url: "/media-storage/primary-320.webp?signed=1",
          },
          {
            name: "1600w",
            mime: "image/webp",
            width: 1600,
            height: 1200,
            sha256: "3".repeat(64),
            url: "/media-storage/primary-1600.webp?signed=1",
          },
        ],
      },
      {
        asset_id: "video",
        kind: "video",
        purpose: "demonstration",
        alt_text: "Демонстрация датчика",
        caption: "Видео подключения",
        display_order: 0,
        is_primary: false,
        width: 1280,
        height: 720,
        variants: [{
          name: "720p",
          mime: "video/mp4",
          width: 1280,
          height: 720,
          sha256: "4".repeat(64),
          url: "/media-storage/demo.mp4?signed=1",
        }],
      },
    ];
    const view = render(<MediaGallery items={items} />);

    const primary = screen.getByRole("img", { name: "Датчик целиком" });
    expect(primary).toHaveAttribute("fetchpriority", "high");
    expect(primary).toHaveAttribute("srcset", expect.stringContaining("1600w"));
    expect(screen.getByText("Основной вид")).toBeVisible();
    expect(screen.getByText("Изображение 1 из 2")).toBeVisible();
    const video = screen.getByLabelText("Демонстрация датчика");
    expect(video).toHaveAttribute("controls");
    expect(video).not.toHaveAttribute("autoplay");

    const primaryThumbnail = screen.getByRole("button", {
      name: "Показать изображение 1: Датчик целиком",
    });
    const secondaryThumbnail = screen.getByRole("button", {
      name: "Показать изображение 2: Разъёмы датчика",
    });
    primaryThumbnail.focus();
    fireEvent.keyDown(primaryThumbnail, { key: "ArrowRight" });
    expect(secondaryThumbnail).toHaveFocus();
    expect(screen.getByRole("img", { name: "Разъёмы датчика" })).toHaveTextContent(
      "Изображение недоступно",
    );
    expect(screen.getByText("Крупный план")).toBeVisible();

    fireEvent.click(primaryThumbnail);
    fireEvent.error(screen.getByRole("img", { name: "Датчик целиком" }));
    expect(screen.getByRole("img", { name: "Датчик целиком" })).toHaveTextContent(
      "Изображение недоступно",
    );

    const renewedItems = items.map((item) => item.asset_id === "primary"
      ? {
          ...item,
          variants: item.variants.map((variant) => ({
            ...variant,
            url: `${variant.url}&renewed=1`,
          })),
        }
      : item);
    view.rerender(<MediaGallery items={renewedItems} />);
    expect(screen.getByRole("img", { name: "Датчик целиком" })).toHaveAttribute(
      "src",
      expect.stringContaining("renewed=1"),
    );
  });

  it("does not invent attribution for manual material", () => {
    const { container } = render(<SourceAttributionBlock sources={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
