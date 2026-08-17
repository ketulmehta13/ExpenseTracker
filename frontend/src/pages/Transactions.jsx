import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
    Plus, Pencil, Trash2, Filter, Download, FileText,
    Search, ChevronUp, ChevronDown, ChevronLeft, ChevronRight,
    ReceiptText, X
} from 'lucide-react';
import { toast } from 'sonner';
import {
    getTransactions, deleteTransaction, getCategories,
    exportTransactionsCSV
} from '../services/api';
import { useAuth } from '../context/AuthContext';
import { formatCurrency, formatDate } from '../lib/formatters';
import { SkeletonTable } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import TransactionModal from '../components/TransactionModal';
import ConfirmModal from '../components/ConfirmModal';
import { jsPDF } from 'jspdf';
import 'jspdf-autotable';

// TODO: Replace with server-side pagination if the Supabase transactions table
// grows beyond ~1000 rows and client-side filtering becomes slow.
const PAGE_SIZE = 25;

const SortIcon = ({ column, sortBy, sortDir }) => {
    if (sortBy !== column) return <span className="inline-block w-3.5 opacity-30">↕</span>;
    return sortDir === 'asc' ? <ChevronUp size={13} className="inline text-primary" /> : <ChevronDown size={13} className="inline text-primary" />;
};

const Transactions = () => {
    const { user } = useAuth();
    const [transactions, setTransactions] = useState([]);
    const [categories, setCategories] = useState([]);
    const [loading, setLoading] = useState(true);

    // Filters
    const [search, setSearch] = useState('');
    const [filterType, setFilterType] = useState('');
    const [filterCategory, setFilterCategory] = useState('');
    const [filterDateFrom, setFilterDateFrom] = useState('');
    const [filterDateTo, setFilterDateTo] = useState('');
    const [filterAmtMin, setFilterAmtMin] = useState('');
    const [filterAmtMax, setFilterAmtMax] = useState('');
    const [showFilters, setShowFilters] = useState(false);

    // Sorting
    const [sortBy, setSortBy] = useState('date');
    const [sortDir, setSortDir] = useState('desc');

    // Pagination
    const [page, setPage] = useState(1);

    // Modals
    const [txModal, setTxModal] = useState({ open: false, transaction: null, type: 'EXPENSE' });
    const [deleteModal, setDeleteModal] = useState({ open: false, id: null, title: '' });
    const [deleting, setDeleting] = useState(false);

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const [txs, cats] = await Promise.all([getTransactions(), getCategories()]);
            setTransactions(txs);
            setCategories(cats);
        } catch (err) {
            toast.error('Failed to load transactions.');
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchData(); }, [fetchData]);

    // Re-fetch when sidebar modal updates
    useEffect(() => {
        const handler = () => fetchData();
        window.addEventListener('transaction-updated', handler);
        return () => window.removeEventListener('transaction-updated', handler);
    }, [fetchData]);

    /* ── Sorting handler ── */
    const handleSort = (col) => {
        if (sortBy === col) {
            setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
        } else {
            setSortBy(col);
            setSortDir('desc');
        }
        setPage(1);
    };

    /* ── Filtered + sorted transactions ── */
    const filtered = useMemo(() => {
        let list = transactions.filter((t) => {
            if (filterType && t.type !== filterType) return false;
            if (filterCategory && t.category_id !== filterCategory) return false;
            if (filterDateFrom && t.date < filterDateFrom) return false;
            if (filterDateTo && t.date > filterDateTo) return false;
            const amt = parseFloat(t.amount);
            if (filterAmtMin && amt < parseFloat(filterAmtMin)) return false;
            if (filterAmtMax && amt > parseFloat(filterAmtMax)) return false;
            if (search) {
                const q = search.toLowerCase();
                if (
                    !t.title?.toLowerCase().includes(q) &&
                    !t.notes?.toLowerCase().includes(q) &&
                    !t.category_name?.toLowerCase().includes(q)
                ) return false;
            }
            return true;
        });

        list.sort((a, b) => {
            let cmp = 0;
            if (sortBy === 'date') cmp = new Date(a.date) - new Date(b.date);
            if (sortBy === 'amount') cmp = parseFloat(a.amount) - parseFloat(b.amount);
            return sortDir === 'asc' ? cmp : -cmp;
        });

        return list;
    }, [transactions, filterType, filterCategory, filterDateFrom, filterDateTo, filterAmtMin, filterAmtMax, search, sortBy, sortDir]);

    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    const clearFilters = () => {
        setSearch('');
        setFilterType('');
        setFilterCategory('');
        setFilterDateFrom('');
        setFilterDateTo('');
        setFilterAmtMin('');
        setFilterAmtMax('');
        setPage(1);
    };

    const hasActiveFilters = filterType || filterCategory || filterDateFrom || filterDateTo || filterAmtMin || filterAmtMax || search;

    /* ── Delete ── */
    const handleDeleteConfirm = async () => {
        setDeleting(true);
        try {
            await deleteTransaction(deleteModal.id);
            toast.success(`"${deleteModal.title}" deleted.`);
            fetchData();
        } catch (err) {
            toast.error('Failed to delete transaction.');
        } finally {
            setDeleting(false);
            setDeleteModal({ open: false, id: null, title: '' });
        }
    };

    /* ── Export ── */
    const handleExportCSV = () => {
        exportTransactionsCSV(filtered);
        toast.success('CSV exported!');
    };

    const handleExportPDF = () => {
        const doc = new jsPDF();
        doc.setFontSize(16);
        doc.text('Expense Tracker — Transactions Report', 14, 20);
        doc.setFontSize(9);
        doc.setTextColor(120);
        doc.text(`Generated: ${new Date().toLocaleString()}`, 14, 28);

        doc.autoTable({
            head: [['Date', 'Title', 'Category', 'Type', 'Amount']],
            body: filtered.map((t) => [
                formatDate(t.date),
                t.title,
                t.category_name || '—',
                t.type,
                `${t.type === 'INCOME' ? '+' : '-'}${formatCurrency(t.amount)}`,
            ]),
            startY: 34,
            theme: 'striped',
            headStyles: { fillColor: [34, 40, 58] },
            styles: { fontSize: 8, cellPadding: 3 },
        });

        doc.save('transactions_report.pdf');
        toast.success('PDF exported!');
    };

    return (
        <div className="space-y-5 page-enter">
            {/* ── Page header ── */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="font-display text-3xl font-bold text-foreground">Transactions</h1>
                    <p className="mt-0.5 text-sm text-muted-foreground">
                        {filtered.length} of {transactions.length} transactions
                    </p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                    <button
                        onClick={() => setTxModal({ open: true, transaction: null, type: 'EXPENSE' })}
                        className="flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-sm hover:opacity-90 transition active:scale-95"
                    >
                        <Plus size={14} /> Add Transaction
                    </button>
                    <button
                        onClick={handleExportCSV}
                        className="flex items-center gap-1.5 rounded-xl border border-border px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted transition-colors"
                    >
                        <Download size={13} /> CSV
                    </button>
                    <button
                        onClick={handleExportPDF}
                        className="flex items-center gap-1.5 rounded-xl border border-border px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted transition-colors"
                    >
                        <FileText size={13} /> PDF
                    </button>
                </div>
            </div>

            {/* ── Search + filter bar ── */}
            <div className="flex flex-col gap-3">
                <div className="flex gap-2">
                    <div className="relative flex-1">
                        <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                        <input
                            type="text"
                            value={search}
                            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                            placeholder="Search title, notes, category…"
                            className="w-full rounded-xl border border-border bg-card pl-9 pr-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-ring/30 focus:border-ring transition"
                        />
                    </div>
                    <button
                        onClick={() => setShowFilters((v) => !v)}
                        className={`flex items-center gap-1.5 rounded-xl border px-3.5 py-2.5 text-sm font-medium transition-colors ${showFilters || hasActiveFilters
                            ? 'border-primary bg-primary/10 text-primary'
                            : 'border-border bg-card text-muted-foreground hover:text-foreground'
                            }`}
                    >
                        <Filter size={15} />
                        Filters
                        {hasActiveFilters && (
                            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground">
                                !
                            </span>
                        )}
                    </button>
                    {hasActiveFilters && (
                        <button
                            onClick={clearFilters}
                            className="flex items-center gap-1 rounded-xl border border-border px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        >
                            <X size={14} />
                            Clear
                        </button>
                    )}
                </div>

                {showFilters && (
                    <div className="rounded-2xl border border-border bg-card p-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 animate-in fade-in slide-in-from-top-2 duration-200">
                        <div>
                            <label className="block text-xs font-medium text-muted-foreground mb-1">Type</label>
                            <select
                                value={filterType}
                                onChange={(e) => { setFilterType(e.target.value); setPage(1); }}
                                className="w-full rounded-lg border border-border bg-background px-2.5 py-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring/30"
                            >
                                <option value="">All</option>
                                <option value="INCOME">Income</option>
                                <option value="EXPENSE">Expense</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-muted-foreground mb-1">Category</label>
                            <select
                                value={filterCategory}
                                onChange={(e) => { setFilterCategory(e.target.value); setPage(1); }}
                                className="w-full rounded-lg border border-border bg-background px-2.5 py-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring/30"
                            >
                                <option value="">All categories</option>
                                {categories.map((c) => (
                                    <option key={c.id} value={c.id}>{c.name}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-muted-foreground mb-1">From date</label>
                            <input
                                type="date"
                                value={filterDateFrom}
                                onChange={(e) => { setFilterDateFrom(e.target.value); setPage(1); }}
                                className="w-full rounded-lg border border-border bg-background px-2.5 py-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring/30"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-muted-foreground mb-1">To date</label>
                            <input
                                type="date"
                                value={filterDateTo}
                                onChange={(e) => { setFilterDateTo(e.target.value); setPage(1); }}
                                className="w-full rounded-lg border border-border bg-background px-2.5 py-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring/30"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-muted-foreground mb-1">Min amount</label>
                            <input
                                type="number"
                                min="0"
                                value={filterAmtMin}
                                onChange={(e) => { setFilterAmtMin(e.target.value); setPage(1); }}
                                placeholder="0"
                                className="w-full rounded-lg border border-border bg-background px-2.5 py-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring/30"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-muted-foreground mb-1">Max amount</label>
                            <input
                                type="number"
                                min="0"
                                value={filterAmtMax}
                                onChange={(e) => { setFilterAmtMax(e.target.value); setPage(1); }}
                                placeholder="∞"
                                className="w-full rounded-lg border border-border bg-background px-2.5 py-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring/30"
                            />
                        </div>
                    </div>
                )}
            </div>

            {/* ── Table ── */}
            {loading ? (
                <SkeletonTable rows={8} />
            ) : filtered.length === 0 ? (
                <EmptyState
                    icon={<ReceiptText size={32} />}
                    title={hasActiveFilters ? 'No results match your filters' : 'No transactions yet'}
                    description={
                        hasActiveFilters
                            ? 'Try adjusting your filters or clearing them to see all transactions.'
                            : 'Use the "+ Add Transaction" button above to record your first income or expense.'
                    }
                    ctaLabel={hasActiveFilters ? 'Clear filters' : '+ Add Transaction'}
                    onCta={hasActiveFilters ? clearFilters : () => setTxModal({ open: true, transaction: null, type: 'EXPENSE' })}
                />
            ) : (
                <>
                    {/* Desktop table */}
                    <div className="hidden md:block rounded-2xl border border-border bg-card overflow-hidden">
                        <table className="w-full text-sm">
                            <thead className="border-b border-border bg-surface-muted">
                                <tr>
                                    <th
                                        className="px-5 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide cursor-pointer hover:text-foreground transition-colors select-none"
                                        onClick={() => handleSort('date')}
                                    >
                                        Date <SortIcon column="date" sortBy={sortBy} sortDir={sortDir} />
                                    </th>
                                    <th className="px-5 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                                        Title
                                    </th>
                                    <th className="px-5 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                                        Category
                                    </th>
                                    <th
                                        className="px-5 py-3.5 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wide cursor-pointer hover:text-foreground transition-colors select-none"
                                        onClick={() => handleSort('amount')}
                                    >
                                        Amount <SortIcon column="amount" sortBy={sortBy} sortDir={sortDir} />
                                    </th>
                                    <th className="px-5 py-3.5 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                                        Actions
                                    </th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border/50">
                                {paginated.map((t) => (
                                    <tr key={t.id} className="hover:bg-muted/30 transition-colors group">
                                        <td className="px-5 py-3.5 text-muted-foreground text-xs whitespace-nowrap">
                                            {formatDate(t.date)}
                                        </td>
                                        <td className="px-5 py-3.5">
                                            <div className="flex items-center gap-2">
                                                <div className={`h-2 w-2 rounded-full flex-shrink-0 ${t.type === 'INCOME' ? 'bg-income' : 'bg-expense'}`} />
                                                <span className="font-medium text-foreground">{t.title}</span>
                                                {t.is_recurring && (
                                                    <span className="rounded-full bg-blue-500/10 text-blue-400 px-2 py-0.5 text-[10px] font-medium">
                                                        Recurring
                                                    </span>
                                                )}
                                            </div>
                                            {t.notes && (
                                                <p className="text-xs text-muted-foreground mt-0.5 pl-4 truncate max-w-xs">{t.notes}</p>
                                            )}
                                        </td>
                                        <td className="px-5 py-3.5">
                                            {t.category_name ? (
                                                <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
                                                    {t.category_name}
                                                </span>
                                            ) : (
                                                <span className="text-muted-foreground/40 text-xs">—</span>
                                            )}
                                        </td>
                                        <td className={`px-5 py-3.5 text-right font-bold tabular-nums ${t.type === 'INCOME' ? 'text-income' : 'text-expense'}`}>
                                            {t.type === 'INCOME' ? '+' : '−'}{formatCurrency(t.amount)}
                                        </td>
                                        <td className="px-5 py-3.5">
                                            <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                                <button
                                                    onClick={() => setTxModal({ open: true, transaction: t, type: t.type })}
                                                    className="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                                                    title="Edit"
                                                >
                                                    <Pencil size={13} />
                                                </button>
                                                <button
                                                    onClick={() => setDeleteModal({ open: true, id: t.id, title: t.title })}
                                                    className="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                                                    title="Delete"
                                                >
                                                    <Trash2 size={13} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {/* Mobile card list */}
                    <div className="md:hidden space-y-2">
                        {paginated.map((t) => (
                            <div
                                key={t.id}
                                className="flex items-center justify-between rounded-xl border border-border bg-card px-4 py-3.5"
                            >
                                <div className="flex items-center gap-3 min-w-0">
                                    <div className={`h-10 w-10 flex-shrink-0 flex items-center justify-center rounded-xl text-sm font-bold ${t.type === 'INCOME' ? 'bg-income/15 text-income' : 'bg-expense/15 text-expense'
                                        }`}>
                                        {(t.category_name || t.title || '?')[0].toUpperCase()}
                                    </div>
                                    <div className="min-w-0">
                                        <p className="font-medium text-foreground text-sm truncate">{t.title}</p>
                                        <p className="text-xs text-muted-foreground">
                                            {formatDate(t.date, 'short')}
                                            {t.category_name && ` · ${t.category_name}`}
                                        </p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                                    <span className={`text-sm font-bold ${t.type === 'INCOME' ? 'text-income' : 'text-expense'}`}>
                                        {t.type === 'INCOME' ? '+' : '−'}{formatCurrency(t.amount)}
                                    </span>
                                    <button
                                        onClick={() => setTxModal({ open: true, transaction: t, type: t.type })}
                                        className="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted"
                                    >
                                        <Pencil size={13} />
                                    </button>
                                    <button
                                        onClick={() => setDeleteModal({ open: true, id: t.id, title: t.title })}
                                        className="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                                    >
                                        <Trash2 size={13} />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Pagination */}
                    {totalPages > 1 && (
                        <div className="flex items-center justify-between px-1">
                            <p className="text-xs text-muted-foreground">
                                Page {page} of {totalPages} · {filtered.length} results
                            </p>
                            <div className="flex items-center gap-1">
                                <button
                                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                                    disabled={page === 1}
                                    className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted disabled:opacity-40 transition-colors"
                                >
                                    <ChevronLeft size={15} />
                                </button>
                                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                                    const p = Math.max(1, Math.min(totalPages - 4, page - 2)) + i;
                                    return (
                                        <button
                                            key={p}
                                            onClick={() => setPage(p)}
                                            className={`h-8 w-8 rounded-lg text-xs font-semibold transition-all ${p === page
                                                ? 'bg-primary text-primary-foreground shadow-sm'
                                                : 'border border-border text-muted-foreground hover:bg-muted'
                                                }`}
                                        >
                                            {p}
                                        </button>
                                    );
                                })}
                                <button
                                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                                    disabled={page === totalPages}
                                    className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted disabled:opacity-40 transition-colors"
                                >
                                    <ChevronRight size={15} />
                                </button>
                            </div>
                        </div>
                    )}
                </>
            )}

            {/* ── Modals ── */}
            <TransactionModal
                isOpen={txModal.open}
                transaction={txModal.transaction}
                defaultType={txModal.type}
                onClose={() => setTxModal({ open: false, transaction: null, type: 'EXPENSE' })}
                onSuccess={fetchData}
            />

            <ConfirmModal
                isOpen={deleteModal.open}
                onClose={() => setDeleteModal({ open: false, id: null, title: '' })}
                onConfirm={handleDeleteConfirm}
                isLoading={deleting}
                title="Delete transaction?"
                message={`"${deleteModal.title}" will be permanently removed. This action cannot be undone.`}
                confirmLabel="Delete"
            />
        </div>
    );
};

export default Transactions;
