import { describe, expect, it } from "vitest";

import type { User } from "../api/contracts";
import { primaryRoleLabel } from "../config/uiLabels";
import { navigationFor } from "./navigation";

const student: User = {
  id: "00000000-0000-0000-0000-000000000001",
  login: "student",
  display_name: "Мария Студентова",
  roles: ["student"],
  permissions: ["components.view"],
};

const editor: User = {
  ...student,
  login: "editor",
  display_name: "Ирина Редакторова",
  roles: ["student", "editor"],
  permissions: [
    "components.view",
    "components.create",
    "components.edit",
    "components.archive",
    "components.submit_for_review",
    "imports.view",
    "imports.create",
    "imports.retry",
    "imports.cancel",
  ],
};

const teacher: User = {
  ...student,
  login: "teacher",
  display_name: "Ольга Преподаватель",
  roles: ["teacher"],
};

const administrator: User = {
  ...student,
  login: "administrator",
  display_name: "Анна Администраторова",
  roles: ["administrator"],
  permissions: [
    "components.view",
    "components.create",
    "components.edit",
    "components.archive",
    "components.review",
    "components.publish",
    "imports.view",
    "imports.create",
    "imports.retry",
    "imports.cancel",
    "users.view",
    "users.manage",
    "roles.assign",
    "system.diagnostics",
  ],
};

function labels(user: User, section: "primary" | "materials" | "administration") {
  return navigationFor(user, section).map((item) => item.label);
}

describe("permission-based navigation", () => {
  it("shows only the catalog to a student", () => {
    expect(labels(student, "primary")).toEqual(["Каталог"]);
    expect(labels(student, "materials")).toEqual([]);
    expect(labels(student, "administration")).toEqual([]);
    expect(primaryRoleLabel(student.roles)).toBe("Ученик");
  });

  it("shows card and upload work to an editor without administration", () => {
    expect(labels(editor, "primary")).toEqual(["Каталог", "Редакция"]);
    expect(labels(editor, "materials")).toEqual([
      "Обзор",
      "Карточки",
      "Новая карточка",
      "Загрузка компонентов",
    ]);
    expect(labels(editor, "administration")).toEqual([]);
    expect(primaryRoleLabel(editor.roles)).toBe("Редактор базы");
  });

  it("uses the Russian teacher label without exposing the workspace", () => {
    expect(labels(teacher, "primary")).toEqual(["Каталог"]);
    expect(labels(teacher, "materials")).toEqual([]);
    expect(labels(teacher, "administration")).toEqual([]);
    expect(primaryRoleLabel(teacher.roles)).toBe("Преподаватель");
  });

  it("shows user management and diagnostics to an administrator", () => {
    expect(labels(administrator, "administration")).toEqual([
      "Пользователи",
      "Диагностика",
    ]);
    expect(primaryRoleLabel(administrator.roles)).toBe("Администратор");
  });

  it("does not trust a role label when server permissions are absent", () => {
    const forgedAdministrator: User = {
      ...student,
      roles: ["administrator"],
    };

    expect(primaryRoleLabel(forgedAdministrator.roles)).toBe("Администратор");
    expect(labels(forgedAdministrator, "primary")).toEqual(["Каталог"]);
    expect(labels(forgedAdministrator, "administration")).toEqual([]);
  });
});
