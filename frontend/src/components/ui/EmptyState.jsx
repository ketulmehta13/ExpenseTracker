import React from 'react';
import { cn } from '../../lib/utils';

/**
 * EmptyState — reusable empty/zero-data placeholder.
 *
 * Props:
 *   icon       — React node (lucide icon component, pre-instantiated)
 *   title      — main heading
 *   description — supporting text
 *   ctaLabel   — CTA button label (optional)
 *   onCta      — CTA click handler (optional)
 *   className  — extra wrapper classes
 */
export function EmptyState({
    icon,
    title,
    description,
    ctaLabel,
    onCta,
    className,
}) {
    return (
        <div
            className={cn(
                'flex flex-col items-center justify-center py-16 px-6 text-center',
                className
            )}
        >
            {icon && (
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground">
                    {icon}
                </div>
            )}
            <h3 className="mb-1 text-base font-semibold text-foreground">{title}</h3>
            {description && (
                <p className="mb-6 max-w-xs text-sm text-muted-foreground leading-relaxed">
                    {description}
                </p>
            )}
            {ctaLabel && onCta && (
                <button
                    onClick={onCta}
                    className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-sm transition hover:opacity-90 active:scale-95"
                >
                    {ctaLabel}
                </button>
            )}
        </div>
    );
}

export default EmptyState;
