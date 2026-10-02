'use client';

/**
 * `useOpenAfterMount(open)` — `false` on the very first render, `open` afterwards.
 *
 * Workaround for a `Dialog` (components/ui) + React StrictMode interaction seen on the dev
 * server: a `<dialog>` that MOUNTS with `open` runs
 * `showModal()` in a layout effect, StrictMode's simulated unmount runs the cleanup's
 * `close()`, the re-mount calls `showModal()` again, and the native `close` event — which is
 * queued asynchronously — then reaches `onNativeClose` with `openRef.current === true`, so the
 * dialog reports itself closed and the caller unmounts it. Opening one tick after mount turns
 * the open into an ordinary update, which StrictMode does not double-invoke.
 */
import { useEffect, useState } from 'react';

export function useOpenAfterMount(open: boolean): boolean {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  return mounted && open;
}
