import type { Permission, User } from "../api/contracts";
import { hasPermission } from "../auth/permissions";

export interface NavigationItem {
  label: string;
  path: string;
  end?: boolean;
  icon: string;
  permission?: Permission;
  section: "primary" | "materials" | "administration";
}

const NAVIGATION_ITEMS: readonly NavigationItem[] = [
  {
    label: "Каталог",
    path: "/",
    end: true,
    icon: "⌕",
    section: "primary",
  },
  {
    label: "Редакция",
    path: "/admin",
    end: false,
    icon: "✎",
    permission: "components.edit",
    section: "primary",
  },
  {
    label: "Обзор",
    path: "/admin",
    end: true,
    icon: "⌂",
    permission: "components.edit",
    section: "materials",
  },
  {
    label: "Карточки",
    path: "/admin/components",
    end: true,
    icon: "▤",
    permission: "components.edit",
    section: "materials",
  },
  {
    label: "Новая карточка",
    path: "/admin/components/new",
    icon: "＋",
    permission: "components.create",
    section: "materials",
  },
  {
    label: "Загрузка компонентов",
    path: "/admin/import",
    icon: "⇣",
    permission: "imports.create",
    section: "materials",
  },
  {
    label: "Проверка импорта",
    path: "/admin/import-reviews",
    icon: "⌕",
    permission: "components.review",
    section: "materials",
  },
  {
    label: "Дубликаты",
    path: "/admin/duplicates",
    icon: "◇",
    permission: "components.review",
    section: "materials",
  },
  {
    label: "Пользователи",
    path: "/admin/users",
    icon: "♙",
    permission: "users.view",
    section: "administration",
  },
  {
    label: "Администраторы",
    path: "/admin/administrators",
    icon: "◆",
    permission: "users.manage",
    section: "administration",
  },
  {
    label: "Диагностика",
    path: "/admin/jobs",
    icon: "↻",
    permission: "system.diagnostics",
    section: "administration",
  },
  {
    label: "Журнал действий",
    path: "/admin/audit",
    icon: "◴",
    permission: "audit.view",
    section: "administration",
  },
] as const;

export function navigationFor(
  user: User,
  section: NavigationItem["section"],
): NavigationItem[] {
  return NAVIGATION_ITEMS.filter(
    (item) =>
      item.section === section &&
      (item.permission === undefined || hasPermission(user, item.permission)),
  );
}
