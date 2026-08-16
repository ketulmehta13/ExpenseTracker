import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, TrendingUp, TrendingDown, Loader2, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { createTransaction, updateTransaction, getCategories } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { formatCurrency } from '../lib/formatters';

/**
 * TransactionModal — shared modal for Add and Edit transactions.
 *
 * Props:
 *   isOpen          — boolean
 *   onClose         — () => void
 *   onSuccess       — () => void  (called after successful save)
 *   defaultType     — 'INCOME' | 'EXPENSE'  (for Add mode)
 *   transaction     — object | null  (if set, opens in Edit mode)
 */
const TransactionModal = ({
    isOpen,
    onClose,
    onSuccess,
    defaultType = 'EXPENSE',
    transaction = null,
}) => {
    const { user } = useAuth();
    const isEdit = Boolean(transaction);

    const [categories, setCategories] = useState([]);
    const [catLoading, setCatLoading] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [errors, setErrors] = useState({});

    const [form, setForm] = useState({
        type: defaultType,
        title: '',
        amount: '',
        category_id: '',
        date: new Date().toISOString().split('T')[0],
        notes: '',
        is_recurring: false,
    });

    const firstInputRef = useRef(null);

    // Populate form when editing
    useEffect(() => {
        if (isOpen) {
            if (transaction) {
                setForm({
                    type: transaction.type || defaultType,
                    title: transaction.title || '',
                    amount: transaction.amount?.toString() || '',
                    category_id: transaction.category_id || '',
                    date: transaction.date || new Date().toISOString().split('T')[0],
                    notes: transaction.notes || '',
                    is_recurring: transaction.is_recurring || false,
                });
            } else {
                setForm({
                    type: defaultType,
                    title: '',
                    amount: '',
                    category_id: '',
                    date: new Date().toISOString().split('T')[0],
                    notes: '',
                    is_recurring: false,
                });
            }
            setErrors({});
            loadCategories();
        }
    }, [isOpen, transaction, defaultType]);

    // Focus first field on open
    useEffect(() => {
        if (isOpen) {
            setTimeout(() => firstInputRef.current?.focus(), 80);
        }
    }, [isOpen]);

    // Escape key
    useEffect(() => {
        if (!isOpen) return;
        const handler = (e) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, [isOpen, onClose]);

    const loadCategories = async () => {
        setCatLoading(true);
        try {
            const data = await getCategories();
            setCategories(data || []);
        } catch {
            setCategories([]);
        } finally {
            setCatLoading(false);
        }
    };

    const set = (key, value) => {
        setForm((prev) => ({ ...prev, [key]: value }));
        setErrors((prev) => ({ ...prev, [key]: undefined }));
    };

    const validate = () => {
        const errs = {};
        if (!form.title.trim()) errs.title = 'Title is required.';
        const amt = parseFloat(form.amount);
        if (!form.amount || isNaN(amt) || amt <= 0)
            errs.amount = 'Enter a valid positive amount.';
        if (!form.date) errs.date = 'Date is required.';
        return errs;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        const errs = validate();
        if (Object.keys(errs).length) {
            setErrors(errs);
            return;
        }

        setSubmitting(true);
        try {
            const payload = {
                type: form.type,
                title: form.title.trim(),
                amount: parseFloat(parseFloat(form.amount).toFixed(2)),
                category_id: form.category_id || null,
                date: form.date,
                notes: form.notes.trim(),
                is_recurring: form.is_recurring,
            };

            if (isEdit) {
                await updateTransaction(transaction.id, payload);
                toast.success('Transaction updated successfully!');
            } else {
                await createTransaction(user.id, payload);
                toast.success(
                    form.type === 'INCOME'
                        ? '💰 Income added!'
                        : '💸 Expense recorded!'
                );
            }

            onSuccess?.();
            onClose();
        } catch (err) {
            toast.error(err.message || 'Failed to save transaction. Please try again.');
        } finally {
            setSubmitting(false);
        }
    };

    if (!isOpen) return null;

    const isIncome = form.type === 'INCOME';

    return (
        <div
            className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4"
            aria-modal="true"
            role="dialog"
            aria-labelledby="tx-modal-title"
        >
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                onClick={onClose}
            />

            {/* Modal panel */}
            <div className="relative z-10 w-full sm:max-w-md rounded-t-3xl sm:rounded-2xl bg-card border-t sm:border border-border shadow-2xl animate-in fade-in slide-in-from-bottom-4 sm:zoom-in-95 duration-300 overflow-hidden">

                {/* Type toggle header */}
                <div className={`px-5 pt-5 pb-3 ${isIncome ? 'bg-income/10' : 'bg-expense/10'}`}>
                    <div className="flex items-center justify-between mb-3">
                        <h2 id="tx-modal-title" className="font-semibold text-foreground text-lg">
                            {isEdit ? 'Edit Transaction' : isIncome ? '+ Add Income' : '+ Add Expense'}
                        </h2>
                        <button
                            type="button"
                            onClick={onClose}
                            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                        >
                            <X size={18} />
                        </button>
                    </div>

                    {/* Type toggle */}
                    <div className="flex gap-2">
                        <button
                            type="button"
                            onClick={() => set('type', 'INCOME')}
                            className={`flex-1 flex items-center justify-center gap-1.5 rounded-xl py-2 text-sm font-semibold transition-all ${
                                isIncome
                                    ? 'bg-income text-income-foreground shadow-sm'
                                    : 'bg-muted text-muted-foreground hover:text-foreground'
                            }`}
                        >
                            <TrendingUp size={15} />
                            Income
                        </button>
                        <button
                            type="button"
                            onClick={() => set('type', 'EXPENSE')}
                            className={`flex-1 flex items-center justify-center gap-1.5 rounded-xl py-2 text-sm font-semibold transition-all ${
                                !isIncome
                                    ? 'bg-expense text-expense-foreground shadow-sm'
                                    : 'bg-muted text-muted-foreground hover:text-foreground'
                            }`}
                        >
                            <TrendingDown size={15} />
                            Expense
                        </button>
                    </div>
                </div>

                {/* Form body */}
                <form onSubmit={handleSubmit} noValidate className="p-5 space-y-4">

                    {/* Title */}
                    <div>
                        <label htmlFor="tx-title" className="block text-sm font-medium text-foreground mb-1">
                            Title <span className="text-destructive">*</span>
                        </label>
                        <input
                            id="tx-title"
                            ref={firstInputRef}
                            type="text"
                            value={form.title}
                            onChange={(e) => set('title', e.target.value)}
                            placeholder={isIncome ? 'e.g. Freelance payment' : 'e.g. Groceries'}
                            className={`w-full rounded-xl border px-3.5 py-2.5 text-sm bg-background text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 transition ${
                                errors.title
                                    ? 'border-destructive focus:ring-destructive/30'
                                    : 'border-border focus:ring-ring/30 focus:border-ring'
                            }`}
                        />
                        {errors.title && <p className="mt-1 text-xs text-destructive">{errors.title}</p>}
                    </div>

                    {/* Amount + Date row */}
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label htmlFor="tx-amount" className="block text-sm font-medium text-foreground mb-1">
                                Amount <span className="text-destructive">*</span>
                            </label>
                            <input
                                id="tx-amount"
                                type="number"
                                min="0.01"
                                step="0.01"
                                value={form.amount}
                                onChange={(e) => set('amount', e.target.value)}
                                placeholder="0.00"
                                className={`w-full rounded-xl border px-3.5 py-2.5 text-sm bg-background text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 transition ${
                                    errors.amount
                                        ? 'border-destructive focus:ring-destructive/30'
                                        : 'border-border focus:ring-ring/30 focus:border-ring'
                                }`}
                            />
                            {errors.amount && <p className="mt-1 text-xs text-destructive">{errors.amount}</p>}
                        </div>
                        <div>
                            <label htmlFor="tx-date" className="block text-sm font-medium text-foreground mb-1">
                                Date <span className="text-destructive">*</span>
                            </label>
                            <input
                                id="tx-date"
                                type="date"
                                value={form.date}
                                onChange={(e) => set('date', e.target.value)}
                                className={`w-full rounded-xl border px-3.5 py-2.5 text-sm bg-background text-foreground outline-none focus:ring-2 transition ${
                                    errors.date
                                        ? 'border-destructive focus:ring-destructive/30'
                                        : 'border-border focus:ring-ring/30 focus:border-ring'
                                }`}
                            />
                            {errors.date && <p className="mt-1 text-xs text-destructive">{errors.date}</p>}
                        </div>
                    </div>

                    {/* Category */}
                    <div>
                        <label htmlFor="tx-category" className="block text-sm font-medium text-foreground mb-1">
                            Category
                        </label>
                        <select
                            id="tx-category"
                            value={form.category_id}
                            onChange={(e) => set('category_id', e.target.value)}
                            disabled={catLoading}
                            className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm bg-background text-foreground outline-none focus:ring-2 focus:ring-ring/30 focus:border-ring transition disabled:opacity-50"
                        >
                            <option value="">— No category —</option>
                            {categories.map((cat) => (
                                <option key={cat.id} value={cat.id}>
                                    {cat.name}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* Notes */}
                    <div>
                        <label htmlFor="tx-notes" className="block text-sm font-medium text-foreground mb-1">
                            Notes <span className="text-muted-foreground font-normal">(optional)</span>
                        </label>
                        <input
                            id="tx-notes"
                            type="text"
                            value={form.notes}
                            onChange={(e) => set('notes', e.target.value)}
                            placeholder="Add a note…"
                            className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm bg-background text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-ring/30 focus:border-ring transition"
                        />
                    </div>

                    {/* Recurring toggle */}
                    <label className="flex items-center gap-2.5 cursor-pointer select-none">
                        <input
                            type="checkbox"
                            id="tx-recurring"
                            checked={form.is_recurring}
                            onChange={(e) => set('is_recurring', e.target.checked)}
                            className="h-4 w-4 rounded border-border text-primary focus:ring-ring"
                        />
                        <span className="text-sm text-foreground">Mark as recurring transaction</span>
                    </label>

                    {/* Action buttons */}
                    <div className="flex gap-3 pt-1">
                        <button
                            type="button"
                            onClick={onClose}
                            disabled={submitting}
                            className="flex-1 rounded-xl border border-border py-2.5 text-sm font-semibold text-foreground transition hover:bg-muted disabled:opacity-50"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={submitting}
                            className={`flex-1 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm font-semibold transition disabled:opacity-50 shadow-sm ${
                                isIncome
                                    ? 'bg-income text-income-foreground hover:opacity-90'
                                    : 'bg-expense text-expense-foreground hover:opacity-90'
                            }`}
                        >
                            {submitting ? (
                                <>
                                    <Loader2 size={15} className="animate-spin" />
                                    Saving…
                                </>
                            ) : isEdit ? 'Update' : 'Save'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default TransactionModal;
