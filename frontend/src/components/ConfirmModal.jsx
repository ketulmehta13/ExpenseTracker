import React, { useEffect, useRef } from 'react';
import { X, AlertTriangle } from 'lucide-react';

/**
 * ConfirmModal — generic confirmation dialog.
 *
 * Props:
 *   isOpen        — boolean
 *   onClose       — () => void
 *   onConfirm     — () => void
 *   title         — string
 *   message       — string | React node
 *   confirmLabel  — string (default: "Confirm")
 *   cancelLabel   — string (default: "Cancel")
 *   isDestructive — boolean (default: true — red confirm button)
 *   isLoading     — boolean (disables confirm while in-flight)
 */
const ConfirmModal = ({
    isOpen,
    onClose,
    onConfirm,
    title = 'Are you sure?',
    message,
    confirmLabel = 'Confirm',
    cancelLabel = 'Cancel',
    isDestructive = true,
    isLoading = false,
}) => {
    const cancelRef = useRef(null);

    // Focus trap & Escape key
    useEffect(() => {
        if (!isOpen) return;
        const handleKey = (e) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', handleKey);
        cancelRef.current?.focus();
        return () => document.removeEventListener('keydown', handleKey);
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    return (
        <div
            className="fixed inset-0 z-[60] flex items-center justify-center p-4"
            aria-modal="true"
            role="dialog"
            aria-labelledby="confirm-title"
        >
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                onClick={onClose}
            />

            {/* Dialog */}
            <div className="relative z-10 w-full max-w-sm rounded-2xl bg-card border border-border shadow-2xl animate-in fade-in zoom-in-95 duration-200">
                {/* Header */}
                <div className="flex items-start gap-3 p-5 pb-3">
                    <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${isDestructive ? 'bg-destructive/10 text-destructive' : 'bg-income/10 text-income'}`}>
                        <AlertTriangle size={20} />
                    </div>
                    <div className="flex-1 min-w-0">
                        <h2
                            id="confirm-title"
                            className="font-semibold text-foreground text-base"
                        >
                            {title}
                        </h2>
                        {message && (
                            <p className="mt-1 text-sm text-muted-foreground leading-relaxed">
                                {message}
                            </p>
                        )}
                    </div>
                    <button
                        onClick={onClose}
                        className="flex-shrink-0 rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                    >
                        <X size={16} />
                    </button>
                </div>

                {/* Actions */}
                <div className="flex gap-2 p-5 pt-2">
                    <button
                        ref={cancelRef}
                        onClick={onClose}
                        disabled={isLoading}
                        className="flex-1 rounded-lg border border-border px-4 py-2.5 text-sm font-semibold text-foreground transition hover:bg-muted disabled:opacity-50"
                    >
                        {cancelLabel}
                    </button>
                    <button
                        onClick={onConfirm}
                        disabled={isLoading}
                        className={`flex-1 rounded-lg px-4 py-2.5 text-sm font-semibold transition disabled:opacity-50 ${
                            isDestructive
                                ? 'bg-destructive text-destructive-foreground hover:opacity-90'
                                : 'bg-primary text-primary-foreground hover:opacity-90'
                        }`}
                    >
                        {isLoading ? (
                            <span className="flex items-center justify-center gap-2">
                                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                                </svg>
                                Processing…
                            </span>
                        ) : confirmLabel}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ConfirmModal;
