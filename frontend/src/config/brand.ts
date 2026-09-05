export const PRODUCT_BRAND = Object.freeze({
  productName: "Справочник электронных компонентов",
  shortName: "База компонентов Arduino",
  authorName: "akiamuradev",
  authorUrl: "https://github.com/akiamuradev",
  officialRepository: "https://github.com/akiamuradev/arduino-component-knowledge-base",
  copyright: "© 2026 akiamuradev",
  licenseName: "PolyForm Noncommercial License 1.0.0",
});

export interface OrganizationBranding {
  organizationName?: string;
  organizationLogoUrl?: string;
  supportEmail?: string;
  supportPhone?: string;
}

function environmentValue(value: string | undefined, fallback: string): string {
  const trimmed = value?.trim();
  return trimmed === undefined || trimmed === "" ? fallback : trimmed;
}

export const BUILD_INFO = Object.freeze({
  version: environmentValue(import.meta.env.VITE_APP_VERSION, "1.0.1"),
  commitSha: environmentValue(
    import.meta.env.VITE_COMMIT_SHA,
    "не указан",
  ),
  buildDate: environmentValue(import.meta.env.VITE_BUILD_DATE, "не указана"),
});
