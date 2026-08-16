import React from 'react';
import { cn } from '../../lib/utils';

/* ─────────────────────────────────────────────
   Generic skeleton pulse block
───────────────────────────────────────────── */
export function Skeleton({ className, ...props }) {
    return (
        <div
            className={cn(
                'animate-pulse rounded-md bg-muted/60',
                className
            )}
            {...props}
        />
    );
}

/* ─────────────────────────────────────────────
   Pre-built: summary card skeleton (x4 grid)
───────────────────────────────────────────── */
export function SkeletonCard() {
    return (
        <div className="rounded-xl border border-border bg-card p-5 space-y-3">
            <div className="flex items-center justify-between">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-8 w-8 rounded-lg" />
            </div>
            <Skeleton className="h-8 w-36" />
            <Skeleton className="h-3 w-20" />
        </div>
    );
}

/* ─────────────────────────────────────────────
   Pre-built: 4-column summary card row
───────────────────────────────────────────── */
export function SkeletonDashboard() {
    return (
        <div className="space-y-6">
            {/* Greeting */}
            <div className="space-y-2">
                <Skeleton className="h-9 w-64" />
                <Skeleton className="h-4 w-44" />
            </div>
            {/* Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                    <SkeletonCard key={i} />
                ))}
            </div>
            {/* Charts row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="rounded-xl border border-border bg-card p-5">
                    <Skeleton className="h-5 w-44 mb-4" />
                    <Skeleton className="h-64 w-full rounded-lg" />
                </div>
                <div className="rounded-xl border border-border bg-card p-5 space-y-3">
                    <Skeleton className="h-5 w-36 mb-4" />
                    {Array.from({ length: 5 }).map((_, i) => (
                        <div key={i} className="flex items-center justify-between py-2">
                            <div className="flex items-center gap-3">
                                <Skeleton className="h-9 w-9 rounded-full" />
                                <div className="space-y-1.5">
                                    <Skeleton className="h-3.5 w-28" />
                                    <Skeleton className="h-3 w-20" />
                                </div>
                            </div>
                            <Skeleton className="h-4 w-16" />
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

/* ─────────────────────────────────────────────
   Pre-built: table rows skeleton
───────────────────────────────────────────── */
export function SkeletonTable({ rows = 8 }) {
    return (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
            {/* Header */}
            <div className="grid grid-cols-4 gap-4 px-6 py-3 border-b border-border bg-surface-muted">
                {['Date', 'Title', 'Amount', 'Actions'].map((col) => (
                    <Skeleton key={col} className="h-4 w-16" />
                ))}
            </div>
            {/* Rows */}
            {Array.from({ length: rows }).map((_, i) => (
                <div
                    key={i}
                    className="grid grid-cols-4 gap-4 px-6 py-4 border-b border-border/50 last:border-0"
                >
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-4 w-36" />
                    <Skeleton className="h-4 w-20" />
                    <div className="flex gap-2 justify-end">
                        <Skeleton className="h-8 w-8 rounded-md" />
                        <Skeleton className="h-8 w-8 rounded-md" />
                    </div>
                </div>
            ))}
        </div>
    );
}

/* ─────────────────────────────────────────────
   Pre-built: chart area skeleton
───────────────────────────────────────────── */
export function SkeletonChart({ height = 280 }) {
    return (
        <div className="rounded-xl border border-border bg-card p-5">
            <Skeleton className="h-5 w-40 mb-1" />
            <Skeleton className="h-3.5 w-28 mb-4" />
            <Skeleton className="w-full rounded-lg" style={{ height }} />
        </div>
    );
}

export default Skeleton;
