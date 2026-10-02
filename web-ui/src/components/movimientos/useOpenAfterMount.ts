'use client';

/**
 * `false` on the first render, `true` from the first effect on. Dialogs that are mounted
 * *because* they are open (the Agregar dialog, the delete confirm) pass this as `open` so the
 * native `<dialog>` is shown by a prop flip rather than at mount: under React StrictMode
 * (every `next dev`) a mount-time `showModal()` is immediately undone by the simulated
 * unmount/remount — `close()` fires the native `close` event, the primitive routes it to
 * `onClose`, and the dialog vanishes before it is seen. Production builds do not double-run
 * effects, so this is only a dev-loop guard.
 */
import { useEffect, useState } from 'react';

export function useOpenAfterMount(): boolean {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    setOpen(true);
  }, []);
  return open;
}
