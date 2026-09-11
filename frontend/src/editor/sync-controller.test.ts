import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { readRecovery, RECOVERY_PREFIX } from "./recovery";
import { SyncController } from "./sync-controller";

interface State { title: string }
interface Card { id: string; title: string; revision: number; edit_token: number }
const initial = { title: "" };
const card: Card = { id: "card", title: "", revision: 1, edit_token: 14 };
const key = `${RECOVERY_PREFIX}user:card`;
const valid = (v: unknown): v is State => typeof v === "object" && v !== null && "title" in v && typeof v.title === "string";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function setup(existing: Card | undefined = card) {
  const create = vi.fn((s: State) => Promise.resolve({ ...card, ...s, edit_token: 1 }));
  const save = vi.fn((s: State, c: Card) => Promise.resolve({ ...c, ...s, edit_token: c.edit_token + 1 }));
  const onCard = vi.fn();
  const sync = new SyncController<State, Card>({ initial, card: existing, recoveryKey: key,
    validateRecovery: valid, validate: (s): Record<string, string> => s.title === "invalid" ? { title: "Invalid" } : {},
    create, save, onCard, acceptMetadata: (local) => local, debounceMs: 750 });
  return { sync, create, save, onCard };
}

beforeEach(() => { localStorage.clear(); vi.useFakeTimers(); });
afterEach(() => { vi.useRealTimers(); localStorage.clear(); });

describe("single-owner document synchronization", () => {
  it("coalesces typing, preserving a one-space edit immediately", async () => {
    const { sync, save } = setup();
    sync.edit({ title: " " });
    expect(sync.snapshot().dirty).toBe(true);
    expect(readRecovery(key, valid)?.state.title).toBe(" ");
    sync.edit({ title: "Arduino" });
    sync.edit({ title: "Arduino UNO R3" });
    expect(save).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(750);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0]?.[0].title).toBe("Arduino UNO R3");
    expect(sync.snapshot().status).toBe("saved");
    expect(localStorage.getItem(key)).toBeNull();
  });

  it("never reverts text from a stale response and sends queued generation with the new token", async () => {
    const { sync, save } = setup();
    const pending = deferred<Card>();
    save.mockImplementationOnce(() => pending.promise);
    sync.edit({ title: "Arduino" });
    const first = sync.flush();
    expect(sync.flush()).toBe(first);
    await vi.advanceTimersByTimeAsync(0);
    sync.edit({ title: "Arduino UNO R3" });
    await vi.advanceTimersByTimeAsync(1000);
    expect(save).toHaveBeenCalledTimes(1);
    pending.resolve({ ...card, title: "Arduino", edit_token: 15 });
    await first;
    expect(sync.snapshot().state.title).toBe("Arduino UNO R3");
    expect(save).toHaveBeenCalledTimes(2);
    expect(save.mock.calls[1]?.[1].edit_token).toBe(15);
    expect(sync.snapshot().card?.revision).toBe(1);
  });

  it("creates exactly one draft and retains edits made during creation", async () => {
    const { sync, create, save } = setup(undefined);
    // Explicit undefined uses JS default parameters; create a new controller directly.
    const pending = deferred<Card>();
    create.mockImplementationOnce(() => pending.promise);
    const fresh = new SyncController<State, Card>({ initial, recoveryKey: key,
      validateRecovery: valid, validate: () => ({}), create, save, onCard: () => undefined,
      acceptMetadata: (local) => local });
    fresh.edit({ title: "A" });
    const request = fresh.flush();
    await vi.advanceTimersByTimeAsync(0);
    fresh.edit({ title: "Arduino UNO" });
    await vi.advanceTimersByTimeAsync(1000);
    expect(create).toHaveBeenCalledTimes(1);
    pending.resolve({ ...card, title: "A", edit_token: 1 });
    await request;
    expect(create).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0]?.[0].title).toBe("Arduino UNO");
    sync.dispose();
  });

  it("preserves network-failed work and allows explicit retry", async () => {
    const { sync, save } = setup();
    save.mockRejectedValueOnce(new ApiError(0, "network_unavailable"));
    sync.edit({ title: "Recover me" });
    await expect(sync.flush()).rejects.toThrow();
    expect(sync.snapshot().status).toBe("error");
    expect(readRecovery(key, valid)?.state.title).toBe("Recover me");
    await sync.flush();
    expect(sync.snapshot().status).toBe("saved");
  });

  it("stops real conflicts and never force-overwrites the server", async () => {
    const { sync, save } = setup();
    save.mockRejectedValueOnce(new ApiError(409, "revision_conflict"));
    sync.edit({ title: "Local" });
    await expect(sync.flush()).rejects.toThrow();
    sync.edit({ title: "Still local" });
    await vi.advanceTimersByTimeAsync(5000);
    await expect(sync.flush()).rejects.toThrow();
    expect(save).toHaveBeenCalledTimes(1);
    expect(sync.snapshot().state.title).toBe("Still local");
  });

  it("recovers local work only after explicit choice and preserves stale base token across reloads", async () => {
    const first = setup();
    first.sync.edit({ title: "Local recovery" });
    first.sync.dispose();
    const next = setup({ ...card, edit_token: 20 });
    expect(next.sync.snapshot().status).toBe("recovery");
    expect(next.save).not.toHaveBeenCalled();
    await next.sync.recover();
    expect(next.sync.snapshot().status).toBe("conflict");
    expect(readRecovery(key, valid)?.token).toBe(14);
    await expect(next.sync.flush()).rejects.toThrow();
  });

  it("does not send known-invalid snapshots and resumes when corrected", async () => {
    const { sync, save } = setup();
    sync.edit({ title: "invalid" });
    await vi.advanceTimersByTimeAsync(2000);
    expect(save).not.toHaveBeenCalled();
    expect(readRecovery(key, valid)?.state.title).toBe("invalid");
    sync.edit({ title: "Valid" });
    await vi.advanceTimersByTimeAsync(750);
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("flushes latest content before a lifecycle command and serializes duplicate intentions", async () => {
    const { sync, save } = setup();
    sync.edit({ title: "Latest content" });
    const command = vi.fn((c: Card) => Promise.resolve({ ...c, revision: 2, edit_token: 16 }));
    const flight = sync.command(command);
    expect(sync.command(command)).toBe(flight);
    await flight;
    expect(save).toHaveBeenCalledOnce();
    expect(command.mock.calls[0]?.[0].edit_token).toBe(15);
    expect(command.mock.calls[0]?.[0].title).toBe("Latest content");
  });

  it("ignores corrupt/schema-invalid recovery without crashing", () => {
    localStorage.setItem(key, "{broken");
    expect(setup().sync.snapshot().status).toBe("saved");
    localStorage.setItem(key, JSON.stringify({ version: 2, state: { title: 1 } }));
    expect(setup().sync.snapshot().recovery).toBeNull();
  });

  it("recovers an already-created draft without a duplicate POST", async () => {
    const { create, save } = setup();
    save.mockRejectedValueOnce(new ApiError(0, "network_unavailable"));
    const options = { initial, recoveryKey: key, validateRecovery: valid,
      validate: () => ({}), create, save, onCard: () => undefined,
      acceptMetadata: (local: State) => local };
    const fresh = new SyncController<State, Card>(options);
    fresh.edit({ title: "Unsaved after creation" });
    await expect(fresh.flush()).rejects.toThrow();
    expect(readRecovery(key, valid)?.componentId).toBe(card.id);
    fresh.dispose();
    const loadCard = vi.fn(() => Promise.resolve({ ...card, edit_token: 1 }));
    const recovered = new SyncController<State, Card>({ ...options, loadCard });
    await recovered.recover();
    await recovered.flush();
    expect(loadCard).toHaveBeenCalledWith(card.id);
    expect(create).toHaveBeenCalledTimes(1);
    expect(recovered.snapshot().state.title).toBe("Unsaved after creation");
    expect(recovered.snapshot().dirty).toBe(false);
  });

  it("blocks lifecycle during a staged upload", async () => {
    const { sync } = setup();
    const command = vi.fn(() => Promise.resolve(card));
    sync.setBusy(true);
    await expect(sync.command(command)).rejects.toThrow("загрузки файлов");
    expect(command).not.toHaveBeenCalled();
    sync.setBusy(false);
    await sync.command(command);
    expect(command).toHaveBeenCalledOnce();
  });

  it("does not restore private recovery after disposal during a fetch", async () => {
    const first = setup();
    first.sync.edit({ title: "Private text" });
    first.sync.dispose();
    const pending = deferred<Card>();
    const recovered = new SyncController<State, Card>({ initial, recoveryKey: key,
      validateRecovery: valid, validate: () => ({}), create: first.create, save: first.save,
      onCard: first.onCard, acceptMetadata: (local) => local, loadCard: () => pending.promise });
    const flight = recovered.recover();
    recovered.dispose();
    localStorage.clear();
    pending.resolve(card);
    await flight;
    expect(recovered.snapshot().state).toEqual(initial);
    expect(localStorage.length).toBe(0);
  });

  it("ignores an upload callback after editor disposal and logout cleanup", async () => {
    const { sync, save } = setup();
    sync.edit({ title: "Private document" });
    sync.dispose();
    localStorage.clear();
    sync.edit({ title: "Late upload attachment" });
    await expect(sync.flush()).rejects.toThrow("Редактор закрыт");
    await vi.advanceTimersByTimeAsync(1000);
    expect(localStorage.length).toBe(0);
    expect(save).not.toHaveBeenCalled();
    expect(sync.snapshot().state.title).toBe("Private document");
  });
});
