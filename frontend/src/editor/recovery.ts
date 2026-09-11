// Only editor document JSON lives here: never session material or upload URLs/bytes.
export const RECOVERY_PREFIX = "ackb:editor:v1:";
const MAX_BYTES = 512_000;
const MAX_ENTRIES = 8;
const TTL = 7 * 24 * 60 * 60 * 1000;

export interface Recovery<S> {
  version: 1;
  savedAt: number;
  token: number | null;
  creationKey: string;
  componentId?: string | null;
  state: S;
}

export function readRecovery<S>(key: string, validate: (value: unknown) => value is S): Recovery<S> | null {
  try {
    const text = localStorage.getItem(key);
    if (!text || text.length > MAX_BYTES) return null;
    const value: unknown = JSON.parse(text);
    if (typeof value !== "object" || value === null) return null;
    const record = value as Partial<Recovery<unknown>>;
    if (record.version !== 1 || typeof record.savedAt !== "number" || !Number.isFinite(record.savedAt)
      || record.savedAt > Date.now() + 60_000
      || Date.now() - record.savedAt > TTL || typeof record.creationKey !== "string"
      || !/^[0-9a-f-]{36}$/i.test(record.creationKey)
      || (record.componentId !== undefined && record.componentId !== null && typeof record.componentId !== "string")
      || (record.token !== null && (!Number.isSafeInteger(record.token) || Number(record.token) < 1))
      || !validate(record.state)) return null;
    return record as Recovery<S>;
  } catch { return null; }
}

export function writeRecovery<S>(key: string, value: Recovery<S>): boolean {
  try {
    const text = JSON.stringify(value);
    if (text.length > MAX_BYTES) return false;
    const keys = Object.keys(localStorage).filter((k) => k.startsWith(RECOVERY_PREFIX) && k !== key);
    // Bound growth without ever touching other application/session storage.
    while (keys.length >= MAX_ENTRIES) {
      const oldest = keys.shift();
      if (oldest) localStorage.removeItem(oldest);
    }
    localStorage.setItem(key, text);
    return true;
  } catch { return false; }
}

export function removeRecovery(key: string): void {
  try { localStorage.removeItem(key); } catch { /* Storage may be disabled. */ }
}

export function clearEditorRecovery(): void {
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith(RECOVERY_PREFIX)) localStorage.removeItem(key);
    }
  } catch { /* Logout must still complete if storage is unavailable. */ }
}
