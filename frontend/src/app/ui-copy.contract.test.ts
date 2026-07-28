import { describe, expect, it } from "vitest";

import { PRODUCT_BRAND } from "../config/brand";

const userInterfaceModules = import.meta.glob<string>(
  [
    "../components/*.tsx",
    "!../components/*.test.tsx",
    "../layouts/*.tsx",
    "../pages/*.tsx",
    "!../pages/*.test.tsx",
    "../routing/*.tsx",
  ],
  { eager: true, import: "default", query: "?raw" },
);

const forbiddenUserCopy = [
  "Arduino Base",
  "Component Knowledge Base",
  "Parser Demo Administrator",
  "Import Jobs",
  "Dashboard недоступен",
  "Загружаем редакционный dashboard",
  "Сохранить draft",
  "Открыть draft",
  "Новый draft",
  "Только administrator",
  "Ожидают retry",
  "failed job",
  "successful",
  "Build information",
  "Developed by",
  "Parser version",
  "Revision policy",
  ">Preview<",
] as const;

describe("Russian user interface copy contract", () => {
  it("uses the approved Russian product names", () => {
    expect(PRODUCT_BRAND.productName).toBe("Справочник электронных компонентов");
    expect(PRODUCT_BRAND.shortName).toBe("База компонентов Arduino");
  });

  it("does not reintroduce key English or demonstration strings", () => {
    const copySurface = Object.values(userInterfaceModules).join("\n");

    for (const forbidden of forbiddenUserCopy) {
      expect(copySurface, `Запрещённая пользовательская строка: ${forbidden}`)
        .not.toContain(forbidden);
    }
  });
});
