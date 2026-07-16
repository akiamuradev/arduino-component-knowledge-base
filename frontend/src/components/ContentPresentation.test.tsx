import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CatalogMedia, ContentProvenance } from "../api/contracts";
import { MediaGallery } from "./MediaGallery";
import { SourceAttributionBlock } from "./SourceAttributionBlock";

const source = {
  sourceName: "Arduino Tex",
  sourceUrl: "https://arduino-tex.ru/news/229/item.html",
  sourceDomain: "arduino-tex.ru",
  importedAt: "2026-07-15T10:00:00Z",
  contentLicense: "Unknown",
};

describe("content presentation", () => {
  it("renders one and multiple real source attributions with safe external links", () => {
    const first: ContentProvenance = { id: "source-1", contentType: "description", source };
    const provenance: ContentProvenance[] = [
      first,
      { id: "source-2", contentType: "specification", source: { ...source, sourceName: "Portal PK", sourceDomain: "portal-pk.ru", sourceUrl: "https://portal-pk.ru/news/10-item.html" } },
    ];
    const view = render(<SourceAttributionBlock provenance={[first]} />);
    const link = screen.getByRole("link", { name: /Arduino Tex/ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText(/Импортировано/)).toBeVisible();
    view.rerender(<SourceAttributionBlock provenance={provenance} />);
    expect(screen.getByText("Описание")).toBeVisible();
    expect(screen.getByText("Характеристики")).toBeVisible();
    expect(screen.getAllByText("Unknown")).toHaveLength(2);
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
    const { container } = render(<SourceAttributionBlock provenance={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
