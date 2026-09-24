export const PRODUCT_BRAND = Object.freeze({
  productName: "Справочник электронных компонентов",
  shortName: "База компонентов Arduino",
  authorName: "akiamuradev",
  authorUrl: "https://github.com/akiamuradev",
  officialRepository: "https://github.com/akiamuradev/arduino-component-knowledge-base",
  copyright: "© 2026 akiamuradev",
  licenseName: "GNU GPL v3.0 или новее",
  licenseSpdx: "GPL-3.0-or-later",
  licenseUrl: "/license",
});

function environmentValue(value: string | undefined, fallback: string): string {
  const trimmed = value?.trim();
  return trimmed === undefined || trimmed === "" ? fallback : trimmed;
}

export const BUILD_INFO = Object.freeze({
  version: environmentValue(import.meta.env.VITE_APP_VERSION, "1.7.4"),
  commitSha: environmentValue(
    import.meta.env.VITE_COMMIT_SHA,
    "не указан",
  ),
  buildDate: environmentValue(import.meta.env.VITE_BUILD_DATE, "не указана"),
});
