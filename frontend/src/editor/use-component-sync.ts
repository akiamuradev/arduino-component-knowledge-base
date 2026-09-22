import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useBlocker } from "react-router-dom";

import { SyncController, type SyncCard, type SyncOptions } from "./sync-controller";

export function useComponentSync<S, C extends SyncCard>(options: SyncOptions<S, C> & {
  onExplicitFailure?: (error: unknown) => void;
}) {
  const explicitFailure = useRef(options.onExplicitFailure);
  useEffect(() => { explicitFailure.current = options.onExplicitFailure; }, [options.onExplicitFailure]);
  const [controller] = useState(() => new SyncController(options));
  const view = useSyncExternalStore(controller.subscribe, controller.snapshot);
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    (view.dirty || view.transientBusy) && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (controller.snapshot().transientBusy) { blocker.reset(); return; }
    void controller.flush().then(() => { blocker.proceed(); }).catch((error: unknown) => {
      blocker.reset();
      explicitFailure.current?.(error);
    });
  }, [blocker, controller]);
  useEffect(() => {
    controller.resume();
    const shortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void controller.flush().catch((error: unknown) => { explicitFailure.current?.(error); });
      }
    };
    const unload = (event: BeforeUnloadEvent) => {
      const current = controller.snapshot();
      if (current.dirty || current.transientBusy) { event.preventDefault(); }
    };
    window.addEventListener("keydown", shortcut);
    window.addEventListener("beforeunload", unload);
    return () => {
      controller.dispose();
      window.removeEventListener("keydown", shortcut);
      window.removeEventListener("beforeunload", unload);
    };
  }, [controller]);
  return { ...view, controller };
}
