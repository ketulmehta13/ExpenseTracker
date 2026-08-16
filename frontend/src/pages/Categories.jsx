import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Pencil, Trash2, Tag, ArrowRightLeft } from 'lucide-react';
import { toast } from 'sonner';
import {
    getCategories, createCategory, updateCategory, deleteCategory,
    getTransactionCountByCategory, reassignTransactionsCategory
} from '../services/api';
import { Skeleton } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import ConfirmModal from '../components/ConfirmModal';

/* ── 12 preset color swatches ── */
const PRESET_COLORS = [
    '#f59e0b', '#4ade80', '#60a5fa', '#f472b6',
    '#a78bfa', '#34d399', '#fb923c', '#38bdf8',
    '#ef4444', '#84cc16', '#e879f9', '#2dd4bf',
];

/* ── Default emoji icons ── */
const PRESET_ICONS = ['🛒', '🍔', '🚗', '💊', '🎬', '✈️', '📚', '💼', '🏠', '💡', '🎁', '🏋️'];

/* ── Category Form Modal ── */
const CategoryFormModal = ({ isOpen, onClose, onSave, category }) => {
    const isEdit = Boolean(category);
    const [name, setName] = useState('');
    const [color, setColor] = useState(PRESET_COLORS[0]);
    const [icon, setIcon] = useState(PRESET_ICONS[0]);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        if (isOpen) {
            setName(category?.name || '');
            setColor(category?.color || PRESET_COLORS[0]);
            setIcon(category?.icon || PRESET_ICONS[0]);
            setError('');
        }
    }, [isOpen, category]);

    useEffect(() => {
        if (!isOpen) return;
        const handler = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, [isOpen, onClose]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!name.trim()) { setError('Category name is required.'); return; }
        setSaving(true);
        try {
            if (isEdit) {
                await updateCategory(category.id, { name: name.trim(), color, icon });
                toast.success(`Category "${name.trim()}" updated!`);
            } else {
                await createCategory({ name: name.trim(), color, icon });
                toast.success(`Category "${name.trim()}" created!`);
            }
            onSave();
            onClose();
        } catch (err) {
            toast.error(err.message || 'Failed to save category.');
        } finally {
            setSaving(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" aria-modal="true">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative z-10 w-full max-w-sm rounded-2xl bg-card border border-border shadow-2xl animate-in fade-in zoom-in-95 duration-200 overflow-hidden">
                <div className="p-5">
                    <h2 className="font-semibold text-foreground text-lg mb-4">
                        {isEdit ? 'Edit Category' : 'New Category'}
                    </h2>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        {/* Name */}
                        <div>
                            <label className="block text-sm font-medium text-foreground mb-1.5">
                                Name <span className="text-destructive">*</span>
                            </label>
                            <input
                                autoFocus
                                type="text"
                                value={name}
                                onChange={(e) => { setName(e.target.value); setError(''); }}
                                placeholder="e.g. Groceries"
                                className={`w-full rounded-xl border px-3.5 py-2.5 text-sm bg-background text-foreground outline-none focus:ring-2 transition ${
                                    error ? 'border-destructive focus:ring-destructive/30' : 'border-border focus:ring-ring/30 focus:border-ring'
                                }`}
                            />
                            {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
                        </div>

                        {/* Icon picker */}
                        <div>
                            <label className="block text-sm font-medium text-foreground mb-1.5">Icon</label>
                            <div className="flex flex-wrap gap-2">
                                {PRESET_ICONS.map((ic) => (
                                    <button
                                        type="button"
                                        key={ic}
                                        onClick={() => setIcon(ic)}
                                        className={`h-9 w-9 rounded-xl text-lg flex items-center justify-center transition-all ${
                                            icon === ic
                                                ? 'ring-2 ring-primary ring-offset-2 ring-offset-card scale-110'
                                                : 'bg-muted hover:scale-105'
                                        }`}
                                    >
                                        {ic}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Color picker */}
                        <div>
                            <label className="block text-sm font-medium text-foreground mb-1.5">Color</label>
                            <div className="flex flex-wrap gap-2">
                                {PRESET_COLORS.map((c) => (
                                    <button
                                        type="button"
                                        key={c}
                                        onClick={() => setColor(c)}
                                        className={`h-7 w-7 rounded-full transition-all ${
                                            color === c ? 'ring-2 ring-offset-2 ring-offset-card ring-foreground scale-110' : 'hover:scale-110'
                                        }`}
                                        style={{ background: c }}
                                    />
                                ))}
                            </div>
                        </div>

                        {/* Preview */}
                        <div className="flex items-center gap-3 rounded-xl bg-muted/50 p-3">
                            <div
                                className="flex h-10 w-10 items-center justify-center rounded-xl text-lg"
                                style={{ background: color + '30' }}
                            >
                                {icon}
                            </div>
                            <span className="font-medium text-foreground">{name || 'Category name'}</span>
                            <div className="ml-auto h-3 w-3 rounded-full" style={{ background: color }} />
                        </div>

                        <div className="flex gap-2 pt-1">
                            <button
                                type="button"
                                onClick={onClose}
                                className="flex-1 rounded-xl border border-border py-2.5 text-sm font-semibold text-foreground hover:bg-muted transition"
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                disabled={saving}
                                className="flex-1 rounded-xl bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 transition disabled:opacity-60"
                            >
                                {saving ? 'Saving…' : isEdit ? 'Update' : 'Create'}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
};

/* ── Reassign Modal ── */
const ReassignModal = ({ isOpen, onClose, onConfirm, categories, deletingCategory, isLoading }) => {
    const [targetId, setTargetId] = useState('');
    const others = categories.filter((c) => c.id !== deletingCategory?.id);

    useEffect(() => {
        if (isOpen && others.length > 0) setTargetId(others[0].id);
    }, [isOpen]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" aria-modal="true">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative z-10 w-full max-w-sm rounded-2xl bg-card border border-border shadow-2xl animate-in fade-in zoom-in-95 duration-200 p-5">
                <div className="flex items-center gap-3 mb-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-expense/10 text-expense">
                        <ArrowRightLeft size={18} />
                    </div>
                    <h2 className="font-semibold text-foreground">Reassign Transactions</h2>
                </div>
                <p className="text-sm text-muted-foreground mb-4">
                    <strong className="text-foreground">"{deletingCategory?.name}"</strong> has linked transactions.
                    Reassign them to another category before deleting.
                </p>
                <div className="mb-4">
                    <label className="block text-sm font-medium text-foreground mb-1.5">Move to</label>
                    <select
                        value={targetId}
                        onChange={(e) => setTargetId(e.target.value)}
                        className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring/30"
                    >
                        {others.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                </div>
                <div className="flex gap-2">
                    <button onClick={onClose} className="flex-1 rounded-xl border border-border py-2.5 text-sm font-semibold text-foreground hover:bg-muted transition">
                        Cancel
                    </button>
                    <button
                        onClick={() => onConfirm(targetId)}
                        disabled={!targetId || isLoading}
                        className="flex-1 rounded-xl bg-destructive py-2.5 text-sm font-semibold text-destructive-foreground hover:opacity-90 transition disabled:opacity-60"
                    >
                        {isLoading ? 'Deleting…' : 'Reassign & Delete'}
                    </button>
                </div>
            </div>
        </div>
    );
};

/* ─────────────────────────────────────
   Categories page
───────────────────────────────────── */
const Categories = () => {
    const [categories, setCategories] = useState([]);
    const [txCounts, setTxCounts] = useState({});
    const [loading, setLoading] = useState(true);

    const [formModal, setFormModal] = useState({ open: false, category: null });
    const [deleteModal, setDeleteModal] = useState({ open: false, category: null });
    const [reassignModal, setReassignModal] = useState({ open: false, category: null });
    const [deleting, setDeleting] = useState(false);

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const cats = await getCategories();
            setCategories(cats);
            // Fetch tx counts for all categories in parallel
            const counts = await Promise.all(
                cats.map((c) => getTransactionCountByCategory(c.id).then((n) => [c.id, n]))
            );
            setTxCounts(Object.fromEntries(counts));
        } catch (err) {
            toast.error('Failed to load categories.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleDeleteClick = async (cat) => {
        const count = txCounts[cat.id] ?? 0;
        if (count > 0) {
            setReassignModal({ open: true, category: cat });
        } else {
            setDeleteModal({ open: true, category: cat });
        }
    };

    const handleDirectDelete = async () => {
        setDeleting(true);
        try {
            await deleteCategory(deleteModal.category.id);
            toast.success(`"${deleteModal.category.name}" deleted.`);
            fetchData();
        } catch (err) {
            toast.error(err.message || 'Failed to delete category.');
        } finally {
            setDeleting(false);
            setDeleteModal({ open: false, category: null });
        }
    };

    const handleReassignAndDelete = async (targetId) => {
        setDeleting(true);
        try {
            await reassignTransactionsCategory(reassignModal.category.id, targetId);
            await deleteCategory(reassignModal.category.id);
            toast.success(`Transactions moved and "${reassignModal.category.name}" deleted.`);
            fetchData();
        } catch (err) {
            toast.error(err.message || 'Failed to reassign and delete.');
        } finally {
            setDeleting(false);
            setReassignModal({ open: false, category: null });
        }
    };

    return (
        <div className="space-y-5 page-enter">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="font-display text-3xl font-bold text-foreground">Categories</h1>
                    <p className="mt-0.5 text-sm text-muted-foreground">
                        {categories.length} categories
                    </p>
                </div>
                <button
                    onClick={() => setFormModal({ open: true, category: null })}
                    className="flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm hover:opacity-90 transition"
                >
                    <Plus size={15} />
                    New category
                </button>
            </div>

            {loading ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                    {Array.from({ length: 8 }).map((_, i) => (
                        <div key={i} className="rounded-2xl border border-border bg-card p-4 space-y-3">
                            <div className="flex items-center gap-3">
                                <Skeleton className="h-10 w-10 rounded-xl" />
                                <Skeleton className="h-4 w-24" />
                            </div>
                            <Skeleton className="h-3 w-16" />
                        </div>
                    ))}
                </div>
            ) : categories.length === 0 ? (
                <EmptyState
                    icon={<Tag size={32} />}
                    title="No categories yet"
                    description="Create categories to organize your income and expenses better."
                    ctaLabel="+ New category"
                    onCta={() => setFormModal({ open: true, category: null })}
                />
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                    {categories.map((cat) => (
                        <div
                            key={cat.id}
                            className="group relative rounded-2xl border border-border bg-card p-4 hover:shadow-md transition-shadow"
                        >
                            <div className="flex items-center gap-3 mb-3">
                                <div
                                    className="flex h-10 w-10 items-center justify-center rounded-xl text-lg flex-shrink-0"
                                    style={{ background: (cat.color || '#f59e0b') + '25' }}
                                >
                                    {cat.icon || '🏷️'}
                                </div>
                                <div className="min-w-0">
                                    <p className="font-semibold text-foreground truncate">{cat.name}</p>
                                    <p className="text-xs text-muted-foreground">
                                        {txCounts[cat.id] ?? 0} transaction{(txCounts[cat.id] ?? 0) !== 1 ? 's' : ''}
                                    </p>
                                </div>
                                <div className="ml-auto flex-shrink-0 h-3 w-3 rounded-full" style={{ background: cat.color || '#f59e0b' }} />
                            </div>

                            {/* Actions — appear on hover */}
                            <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                    onClick={() => setFormModal({ open: true, category: cat })}
                                    className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-border py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                                >
                                    <Pencil size={12} />
                                    Edit
                                </button>
                                <button
                                    onClick={() => handleDeleteClick(cat)}
                                    className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-border py-1.5 text-xs font-medium text-muted-foreground hover:text-destructive hover:bg-destructive/10 hover:border-destructive/30 transition-colors"
                                >
                                    <Trash2 size={12} />
                                    Delete
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Modals */}
            <CategoryFormModal
                isOpen={formModal.open}
                category={formModal.category}
                onClose={() => setFormModal({ open: false, category: null })}
                onSave={fetchData}
            />

            <ConfirmModal
                isOpen={deleteModal.open}
                onClose={() => setDeleteModal({ open: false, category: null })}
                onConfirm={handleDirectDelete}
                isLoading={deleting}
                title="Delete category?"
                message={`"${deleteModal.category?.name}" will be permanently removed.`}
                confirmLabel="Delete"
            />

            <ReassignModal
                isOpen={reassignModal.open}
                onClose={() => setReassignModal({ open: false, category: null })}
                onConfirm={handleReassignAndDelete}
                categories={categories}
                deletingCategory={reassignModal.category}
                isLoading={deleting}
            />
        </div>
    );
};

export default Categories;
