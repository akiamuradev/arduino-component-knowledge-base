import type { Permission, User } from "../api/contracts";

export function hasPermission(user: User, permission: Permission): boolean {
  return user.permissions.includes(permission);
}

export function hasAnyPermission(
  user: User,
  permissions: readonly Permission[],
): boolean {
  return permissions.some((permission) => hasPermission(user, permission));
}
