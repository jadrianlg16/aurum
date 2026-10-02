'use client';

/**
 * Dialog / Sheet / ConfirmDialog on the native `<dialog>` element.
 *
 * - `showModal()` runs in a layout effect when `open` flips true (only when connected and not
 *   already open — it throws otherwise) and `close()` when it flips false or the component
 *   unmounts; focus goes back to the opener afterwards, once the top layer is gone.
 * - Esc arrives as the `cancel` event and is routed through `onClose`; a click on the backdrop
 *   (`e.target === dialog`) closes too.
 * - Initial focus: `initialFocus` ref, else `[data-autofocus]`, else the first focusable — and
 *   never stolen from a child that already focused itself (the amount field in "+ Agregar"
 *   does that in its own effect, which React runs before this parent's).
 * - `form` mode wraps the body in a `<form>` so Enter submits; `busy` disables the primary and
 *   marks it `aria-busy`. The footer is sticky; the body scrolls internally.
 * - At ≤640px the CSS turns every Dialog into a bottom sheet; `Sheet` is anchored bottom at
 *   every width. `:root:has(dialog[open])` locks body scroll (globals.css).
 * - Toasts must fire after a dialog closes: the top layer would cover them (ToastProvider
 *   defers them itself).
 */
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  type FormEvent,
  type ReactNode,
  type RefObject,
} from 'react';
import { useI18n } from '@/lib/i18n';
import { Button, IconButton } from './Button';

export type DialogSize = 'sm' | 'md' | 'lg';

export interface DialogFormMode {
  onSubmit: () => void;
  busy?: boolean;
  submitLabel?: string;
}

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  size?: DialogSize;
  /** Enter submits, the footer shows Cancelar + the primary action. */
  form?: DialogFormMode;
  /** Custom footer (ignored in `form` mode). */
  footer?: ReactNode;
  /** `role="alertdialog"` and a danger primary. */
  destructive?: boolean;
  /** Element to focus on open; else `[data-autofocus]`, else the first focusable. */
  initialFocus?: RefObject<HTMLElement | null>;
  /** Server/validation error shown above the footer (form mode). */
  error?: string | null;
  /** Hide the × in the header (Confirm dialogs). */
  hideClose?: boolean;
  /** Internal: render as a bottom sheet at every width. */
  sheet?: boolean;
  className?: string;
  children?: ReactNode;
}

const FOCUSABLE =
  'input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

export function Dialog({
  open,
  onClose,
  title,
  description,
  size = 'md',
  form,
  footer,
  destructive,
  initialFocus,
  error,
  hideClose,
  sheet,
  className,
  children,
}: DialogProps) {
  const { t } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);
  const openRef = useRef(open);
  openRef.current = open;
  const titleId = useId();
  const descId = useId();

  // Open/close the native element. The cleanup closes it and returns focus to whoever opened
  // it — the opener is captured here, before showModal() moves focus inside.
  useLayoutEffect(() => {
    const d = ref.current;
    if (!d || !open) return undefined;
    const opener = document.activeElement as HTMLElement | null;
    if (d.isConnected && !d.open) {
      try {
        d.showModal();
      } catch {
        d.setAttribute('open', '');
      }
    }
    return () => {
      if (d.open) d.close();
      if (opener && opener.isConnected && typeof opener.focus === 'function') {
        opener.focus({ preventScroll: true });
      }
    };
  }, [open]);

  // Initial focus, after the children's own effects have run.
  useEffect(() => {
    const d = ref.current;
    if (!d || !open) return;
    const explicit = initialFocus?.current ?? d.querySelector<HTMLElement>('[data-autofocus]');
    if (explicit) {
      explicit.focus();
      return;
    }
    if (d.contains(document.activeElement) && document.activeElement !== d) return;
    d.querySelector<HTMLElement>(FOCUSABLE)?.focus();
  }, [open, initialFocus]);

  const onCancel = useCallback(
    (e: Event) => {
      e.preventDefault();
      if (openRef.current) onClose();
    },
    [onClose],
  );
  const onNativeClose = useCallback(() => {
    // Closed by the browser (e.g. a second Esc the UA refuses to cancel): keep state in sync.
    // A `close` event queued by an earlier d.close() — React StrictMode's simulated unmount in
    // `next dev` closes and re-shows the element — arrives while the dialog is open again;
    // that one is stale and must not close the dialog a person just saw open.
    if (ref.current?.open) return;
    if (openRef.current) onClose();
  }, [onClose]);

  useEffect(() => {
    const d = ref.current;
    if (!d) return undefined;
    d.addEventListener('cancel', onCancel);
    d.addEventListener('close', onNativeClose);
    return () => {
      d.removeEventListener('cancel', onCancel);
      d.removeEventListener('close', onNativeClose);
    };
  }, [onCancel, onNativeClose]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (form && !form.busy) form.onSubmit();
  };

  const head = (
    <div className="ui-dialog-head">
      <h2 id={titleId}>{title}</h2>
      {!hideClose && <IconButton icon="x" ariaLabel={t('a11y.close_dialog')} onClick={onClose} />}
    </div>
  );
  const desc = description ? (
    <p className="ui-dialog-desc" id={descId}>
      {description}
    </p>
  ) : null;
  const body = <div className="ui-dialog-body">{children}</div>;
  const foot = form ? (
    <div className="ui-dialog-foot">
      <Button variant="ghost" onClick={onClose} disabled={form.busy}>
        {t('common.cancel')}
      </Button>
      <span className="spacer" />
      <Button type="submit" variant={destructive ? 'danger' : 'primary'} loading={form.busy} disabled={form.busy}>
        {form.submitLabel ?? t('common.save')}
      </Button>
    </div>
  ) : footer ? (
    <div className="ui-dialog-foot">{footer}</div>
  ) : null;
  const err = error ? (
    <p className="ui-dialog-error" role="alert">
      {error}
    </p>
  ) : null;

  const cls = ['ui-dialog', size, sheet ? 'ui-sheet' : '', className].filter(Boolean).join(' ');

  return (
    // The backdrop click is a pointer convenience; Esc (the `cancel` event) is the keyboard path.
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={ref}
      className={cls}
      role={destructive ? 'alertdialog' : undefined}
      aria-labelledby={titleId}
      aria-describedby={description ? descId : undefined}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {open &&
        (form ? (
          <form onSubmit={submit} aria-busy={form.busy || undefined}>
            {head}
            {desc}
            {body}
            {err}
            {foot}
          </form>
        ) : (
          <div className="ui-dialog-inner">
            {head}
            {desc}
            {body}
            {err}
            {foot}
          </div>
        ))}
    </dialog>
  );
}

/** A bottom sheet at every width: menus, row actions, filters. */
export function Sheet(props: Omit<DialogProps, 'sheet' | 'size'>) {
  return <Dialog {...props} sheet size="md" />;
}

export interface ConfirmDialogProps {
  open?: boolean;
  title: string;
  /** Formatted content (`<Money>`, dates) — never a raw amount string. */
  body?: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Yes/no on top of Dialog; `destructive` makes it an alertdialog with a danger primary. */
export function ConfirmDialog({
  open = true,
  title,
  body,
  confirmLabel,
  destructive,
  busy,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useI18n();
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      destructive={destructive}
      hideClose
      footer={
        <>
          {/* A destructive confirm starts on Cancelar, so Enter never deletes by accident. */}
          <Button variant="ghost" onClick={onCancel} disabled={busy} data-autofocus={destructive || undefined}>
            {t('common.cancel')}
          </Button>
          <span className="spacer" />
          <Button
            variant={destructive ? 'danger' : 'primary'}
            onClick={onConfirm}
            loading={busy}
            data-autofocus={destructive ? undefined : true}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {body}
    </Dialog>
  );
}
