import { ApiError } from "../api/client";
import { readRecovery, removeRecovery, writeRecovery, type Recovery } from "./recovery";

export type SyncStatus = "saved" | "dirty" | "syncing" | "invalid" | "error" | "conflict" | "recovery";
export interface SyncCard { id: string; revision: number; edit_token?: number }
export interface SyncView<S, C> {
  state: S;
  card: C | undefined;
  status: SyncStatus;
  error: unknown;
  fieldErrors: Record<string, string>;
  dirty: boolean;
  localStored: boolean;
  recovery: Recovery<S> | null;
  commandPending: boolean;
  transientBusy: boolean;
}

export interface SyncOptions<S, C extends SyncCard> {
  initial: S;
  card?: C;
  recoveryKey: string;
  validateRecovery: (value: unknown) => value is S;
  validate: (state: S) => Record<string, string>;
  create: (state: S, creationKey: string) => Promise<C>;
  save: (state: S, card: C) => Promise<C>;
  acceptMetadata: (local: S, card: C) => S;
  onCard: (card: C) => void;
  onSettled?: (card: C) => void;
  loadCard?: (id: string) => Promise<C>;
  debounceMs?: number;
}

export class SyncController<S, C extends SyncCard> {
  private view: SyncView<S, C>;
  private listeners = new Set<() => void>();
  private generation = 0;
  private acknowledged = 0;
  private active: Promise<void> | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private creationKey: string = crypto.randomUUID();
  private disposed = false;
  private baseToken: number | null;
  private commandFlight: Promise<C> | null = null;
  private isDisposed(): boolean { return this.disposed; }

  constructor(private options: SyncOptions<S, C>) {
    this.baseToken = options.card?.edit_token ?? options.card?.revision ?? null;
    const recovery = readRecovery(options.recoveryKey, options.validateRecovery);
    this.view = { state: options.initial, card: options.card,
      status: recovery ? "recovery" : "saved", error: null, fieldErrors: {}, dirty: false,
      localStored: recovery !== null, recovery, commandPending: false, transientBusy: false };
  }

  snapshot = (): SyncView<S, C> => this.view;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  private publish(patch: Partial<SyncView<S, C>>) {
    this.view = { ...this.view, ...patch };
    for (const listener of this.listeners) listener();
  }
  private persist() {
    const localStored = writeRecovery(this.options.recoveryKey, {
      version: 1, savedAt: Date.now(), token: this.baseToken,
      creationKey: this.creationKey, componentId: this.view.card?.id ?? null, state: this.view.state,
    });
    this.publish({ localStored });
  }
  edit = (state: S): void => {
    if (this.disposed || this.view.commandPending || this.view.recovery) return;
    this.generation++;
    const fieldErrors = this.options.validate(state);
    const blocked = this.view.status === "conflict";
    this.publish({ state, dirty: true, fieldErrors, error: blocked ? this.view.error : null,
      status: blocked ? "conflict" : Object.keys(fieldErrors).length ? "invalid" : "dirty" });
    this.persist();
    this.clearTimer();
    if (!blocked && !Object.keys(fieldErrors).length) {
      this.timer = setTimeout(() => { void this.flush().catch(() => undefined); }, this.options.debounceMs ?? 750);
    }
  };
  private clearTimer() {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }
  flush = (): Promise<void> => {
    if (this.disposed) return Promise.reject(new Error("Редактор закрыт"));
    this.clearTimer();
    if (this.active) return this.active;
    if (this.view.recovery || this.view.status === "conflict" || Object.keys(this.view.fieldErrors).length) {
      return Promise.reject(new Error("Синхронизация требует проверки локальных изменений"));
    }
    if (!this.view.dirty) return Promise.resolve();
    // Assign the guard synchronously, before any asynchronous request can start.
    this.active = Promise.resolve().then(() => this.drain()).finally(() => { this.active = null; });
    return this.active;
  };
  private async drain() {
    while (this.acknowledged !== this.generation) {
      if (this.isDisposed()) return;
      if (Object.keys(this.view.fieldErrors).length) {
        this.publish({ status: "invalid" });
        throw new Error("Исправьте ошибки полей");
      }
      const sentGeneration = this.generation;
      const sentState = this.view.state;
      const creating = this.view.card === undefined;
      this.publish({ status: "syncing", error: null });
      try {
        const card = this.view.card === undefined
          ? await this.options.create(sentState, this.creationKey)
          : await this.options.save(sentState, this.view.card);
        if (this.disposed) return;
        this.publish({ card, state: creating ? this.options.acceptMetadata(this.view.state, card) : this.view.state });
        this.options.onCard(card);
        if (creating) {
          // A recovered idempotent POST may return an already edited card: don't overwrite it.
          if ((card.edit_token ?? card.revision) !== 1) {
            throw new ApiError(409, "revision_conflict");
          }
          this.baseToken = card.edit_token ?? card.revision;
          // Always sync latest local state after creation; never mistake an old POST response
          // for acknowledgement of a newer recovered snapshot.
        } else {
          this.acknowledged = sentGeneration;
          this.baseToken = card.edit_token ?? card.revision;
        }
        this.persist();
      } catch (error) {
        if (this.disposed) return;
        this.publish({ status: error instanceof ApiError && error.code === "revision_conflict"
          ? "conflict" : "error", error, dirty: true });
        this.persist();
        throw error;
      }
    }
    removeRecovery(this.options.recoveryKey);
    this.publish({ status: "saved", dirty: false, localStored: false, error: null });
    if (this.view.card) this.options.onSettled?.(this.view.card);
  }
  recover = async (): Promise<void> => {
    const recovery = this.view.recovery;
    if (!recovery) return;
    if (!this.view.card && recovery.componentId && this.options.loadCard) {
      try {
        const loaded = await this.options.loadCard(recovery.componentId);
        if (this.disposed || this.view.recovery !== recovery) return;
        this.publish({ card: loaded });
      } catch (error) {
        if (this.disposed) return;
        this.publish({ error });
        return;
      }
    }
    this.creationKey = recovery.creationKey;
    this.baseToken = recovery.token;
    this.publish({ recovery: null });
    this.edit(recovery.state);
    const token = this.view.card?.edit_token ?? this.view.card?.revision ?? null;
    if (token !== recovery.token) {
      this.clearTimer();
      this.publish({ status: "conflict", error: new ApiError(409, "revision_conflict") });
    }
  };
  discard = (card?: C, state?: S): void => {
    if (this.active || this.commandFlight) return;
    this.clearTimer();
    removeRecovery(this.options.recoveryKey);
    this.generation = this.acknowledged = 0;
    this.baseToken = card?.edit_token ?? card?.revision ?? this.options.card?.edit_token ?? this.options.card?.revision ?? null;
    this.publish({ state: state ?? this.options.initial,
      card: card ?? this.options.card, status: "saved", dirty: false, recovery: null,
      error: null, fieldErrors: {}, localStored: false });
  };
  command = (operation: (card: C) => Promise<C>): Promise<C> => {
    if (this.isDisposed()) return Promise.reject(new Error("Редактор закрыт"));
    if (this.view.transientBusy) return Promise.reject(new Error("Дождитесь окончания загрузки файлов"));
    if (this.commandFlight) return this.commandFlight;
    this.publish({ commandPending: true });
    this.commandFlight = Promise.resolve().then(async () => {
      await this.flush();
      if (this.isDisposed()) throw new Error("Редактор закрыт");
      if (!this.view.card) throw new Error("Сначала начните редактировать карточку");
      const card = await operation(this.view.card);
      if (this.disposed) return card;
      this.baseToken = card.edit_token ?? card.revision;
      this.publish({ card, status: "saved", error: null });
      this.options.onCard(card);
      return card;
    }).catch((error: unknown) => {
      this.publish({ error, status: error instanceof ApiError && error.code === "revision_conflict"
        ? "conflict" : "error" });
      throw error;
    }).finally(() => { this.commandFlight = null; this.publish({ commandPending: false }); });
    return this.commandFlight;
  };
  dispose = (): void => { this.disposed = true; this.clearTimer(); };
  resume = (): void => { this.disposed = false; };
  setBusy = (busy: boolean): void => { this.publish({ transientBusy: busy }); };
}
