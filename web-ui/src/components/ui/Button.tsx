'use client';

/**
 * Buttons. `Button` renders `<a class="btn">` when `href`
 * is given and `<button>` otherwise; `loading` disables it and shows a spinner while keeping
 * the label (so the width never jumps). `IconButton` requires an accessible name.
 */
import Link from 'next/link';
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { Icon, type IconName } from './Icon';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type'> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: IconName;
  href?: string;
  type?: 'button' | 'submit' | 'reset';
  children?: ReactNode;
}

export function buttonClass(variant: ButtonVariant = 'secondary', size: ButtonSize = 'md', extra?: string): string {
  return ['btn', variant === 'secondary' ? '' : variant, size === 'md' ? '' : size, extra].filter(Boolean).join(' ');
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading = false, icon, href, type = 'button', className, children, disabled, ...rest },
  ref,
) {
  const cls = buttonClass(variant, size, className);
  const body = (
    <>
      {loading ? <span className="btn-spin" aria-hidden="true" /> : icon ? <Icon name={icon} size={16} /> : null}
      {children}
    </>
  );
  if (href) {
    return (
      <Link href={href} className={cls}>
        {body}
      </Link>
    );
  }
  return (
    <button ref={ref} type={type} className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {body}
    </button>
  );
});

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type' | 'aria-label'> {
  /** Required: an icon-only control needs a name. */
  ariaLabel: string;
  icon: IconName;
  size?: number;
  bordered?: boolean;
  type?: 'button' | 'submit';
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { ariaLabel, icon, size = 18, bordered, type = 'button', className, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={['iconbtn', bordered ? 'bordered' : '', className].filter(Boolean).join(' ')}
      aria-label={ariaLabel}
      title={ariaLabel}
      {...rest}
    >
      <Icon name={icon} size={size} />
    </button>
  );
});
