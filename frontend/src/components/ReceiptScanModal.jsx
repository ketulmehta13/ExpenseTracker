import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, Camera, ChevronDown, FileText, FileUp, Loader2, ScanLine, X } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { createTransactions, getCategories, uploadReceipt } from '../services/api';
import { scanReceipt, wakeMlService } from '../services/mlService';
import { prepareReceiptFile } from '../lib/receiptFile';
import { todayISODate } from '../lib/dates';
import { formatCurrency } from '../lib/formatters';

const GROUP_NAMES = {
    groceries: 'Groceries', dining: 'Dining', household: 'Household', personal_care: 'Personal care',
    health: 'Health', baby: 'Baby care', pet: 'Pet care', stationery: 'Stationery',
    electronics: 'Electronics', clothing: 'Clothing', fuel: 'Fuel', other: 'Other',
};
// "household+personal_care" -> "Household & personal care"
const groupLabel = (key) => key.split('+')
    .map((part, index) => {
        const name = GROUP_NAMES[part] || part;
        return index ? name.toLowerCase() : name;
    })
    .join(' & ');

const WARNINGS = {
    low_confidence: 'The photo was hard to read. Check the amounts before saving.',
    total_guessed: "There's no clear total line, so the largest amount was used. Please check it.",
    no_total: 'No total was found. Enter it before saving.',
    no_date: 'No date was found, so today is used.',
    no_merchant: "The shop's name wasn't found. Add it before saving.",
    items_dont_add_up: "The items don't add up to the total, so it's set to one transaction.",
};

const money = (value) => (Number.isFinite(value) ? formatCurrency(value) : '—');
const toNumber = (value) => {
    const number = parseFloat(value);
    return Number.isFinite(number) ? Math.round(number * 100) / 100 : NaN;
};

/**
 * ReceiptScanModal: photograph or upload a bill, review what was read, save it as one
 * transaction or split by category. The bill file is stored privately and linked to the
 * transactions on Save; nothing is stored before that.
 */
const ReceiptScanModal = ({ isOpen, onClose }) => {
    const { user } = useAuth();
    const [stage, setStage] = useState('pick'); // pick -> reading -> review
    const [prepared, setPrepared] = useState(null); // { file, kind, previewUrl }
    const [reading, setReading] = useState('');
    const [slow, setSlow] = useState(false);
    const [error, setError] = useState('');
    const [result, setResult] = useState(null);
    const [categories, setCategories] = useState([]);
    const [merchant, setMerchant] = useState('');
    const [date, setDate] = useState(todayISODate());
    const [total, setTotal] = useState('');
    const [split, setSplit] = useState(false);
    const [groups, setGroups] = useState([]);
    const [singleCategory, setSingleCategory] = useState('');
    const [openGroup, setOpenGroup] = useState(null);
    const [showText, setShowText] = useState(false);
    const [saving, setSaving] = useState(false);
    const abortRef = useRef(null);
    const cameraRef = useRef(null);
    const uploadRef = useRef(null);

    const reset = useCallback(() => {
        abortRef.current?.abort();
        setPrepared((current) => {
            if (current?.previewUrl) URL.revokeObjectURL(current.previewUrl);
            return null;
        });
        setStage('pick');
        setError('');
        setResult(null);
        setSlow(false);
        setShowText(false);
        setOpenGroup(null);
    }, []);

    useEffect(() => {
        if (!isOpen) return undefined;
        wakeMlService(); // a sleeping free server wakes while the user picks a file
        getCategories().then((data) => setCategories(data || [])).catch(() => setCategories([]));
        return reset;
    }, [isOpen, reset]);

    const close = useCallback(() => {
        if (saving) return;
        reset();
        onClose();
    }, [saving, reset, onClose]);

    useEffect(() => {
        if (!isOpen) return undefined;
        const handler = (event) => { if (event.key === 'Escape') close(); };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, [isOpen, close]);

    const showResult = (scan) => {
        setResult(scan);
        setMerchant(scan.merchant || '');
        setDate(scan.date || todayISODate());
        setTotal(scan.total != null ? scan.total.toFixed(2) : '');
        const editable = scan.groups.map((group) => ({
            key: group.key,
            label: groupLabel(group.key),
            categoryId: group.category_id != null ? String(group.category_id) : '',
            amount: group.amount.toFixed(2),
            items: group.items,
            include: true,
        }));
        setGroups(editable);
        const canSplit = editable.length >= 2 && !scan.warnings.includes('items_dont_add_up');
        setSplit(canSplit);
        const single = scan.suggestion?.category_id ?? scan.groups[0]?.category_id;
        setSingleCategory(single != null ? String(single) : '');
        setStage('review');
    };

    const handleFile = async (file) => {
        if (!file) return;
        setError('');
        setStage('reading');
        setReading('Preparing the photo…');
        setSlow(false);
        const controller = new AbortController();
        abortRef.current = controller;
        const slowTimer = setTimeout(() => setSlow(true), 12000);
        try {
            const ready = await prepareReceiptFile(file);
            setPrepared(ready);
            setReading(ready.kind === 'pdf' ? 'Reading the PDF…' : 'Reading the bill…');
            const scan = await scanReceipt(ready.file, todayISODate(), controller.signal);
            if (!scan) throw new Error('The bill reader is not available right now.');
            showResult(scan);
        } catch (err) {
            if (controller.signal.aborted) return;
            setError(err.message || 'Could not read the bill.');
            setStage('pick');
        } finally {
            clearTimeout(slowTimer);
        }
    };

    const onPick = (event) => {
        const [file] = event.target.files || [];
        event.target.value = ''; // picking the same file again still fires
        handleFile(file);
    };

    const onDrop = (event) => {
        event.preventDefault();
        handleFile(event.dataTransfer.files?.[0]);
    };

    const totalValue = toNumber(total);
    const included = groups.filter((group) => group.include);
    const groupsSum = included.reduce((sum, group) => sum + (toNumber(group.amount) || 0), 0);
    const mismatch = split && Number.isFinite(totalValue) && Math.abs(groupsSum - totalValue) > 1;
    const canSave = !saving && (split
        ? included.length > 0 && included.every((group) => toNumber(group.amount) > 0)
        : totalValue > 0);

    const handleSave = async () => {
        if (!canSave) return;
        setSaving(true);
        try {
            let receiptPath = null;
            try {
                receiptPath = await uploadReceipt(prepared.file);
            } catch (err) {
                console.warn('Storing the bill failed:', err);
                toast.warning('The bill could not be stored, so the transactions are saved without it.');
            }
            const shop = merchant.trim() || 'Bill';
            const base = { date, type: 'EXPENSE', is_recurring: false, notes: '', receipt_path: receiptPath };
            const rows = split
                ? included.map((group) => ({
                    ...base,
                    title: `${shop} · ${group.label}`,
                    amount: toNumber(group.amount),
                    category_id: group.categoryId || null,
                }))
                : [{ ...base, title: shop, amount: totalValue, category_id: singleCategory || null }];
            const { linked } = await createTransactions(user.id, rows);
            toast.success(rows.length > 1
                ? `${rows.length} transactions saved from your ${shop} bill`
                : `Saved ${shop} · ${formatCurrency(rows[0].amount)}`);
            if (receiptPath && !linked) {
                toast.info('Saved. Linking bills to transactions needs a database update; see the docs.');
            }
            window.dispatchEvent(new CustomEvent('transaction-updated'));
            setSaving(false);
            reset();
            onClose();
        } catch (err) {
            toast.error(err.message || 'Could not save. Please try again.');
            setSaving(false);
        }
    };

    if (!isOpen) return null;

    const updateGroup = (index, changes) =>
        setGroups((current) => current.map((group, i) => (i === index ? { ...group, ...changes } : group)));

    const fieldClass = 'rounded-xl border border-border px-3 py-2 text-sm bg-background text-foreground '
        + 'outline-none focus:ring-2 focus:ring-ring/30 focus:border-ring transition';
    const inputClass = `w-full ${fieldClass}`;
    const categoryOptions = (
        <>
            <option value="" disabled hidden>Select a category</option>
            {categories.map((category) => (
                <option key={category.id} value={category.id}>{category.name}</option>
            ))}
        </>
    );

    return createPortal(
        <div
            className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="scan-title"
        >
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={close} />
            <div className="relative z-10 w-full sm:max-w-lg max-h-[90dvh] overflow-y-auto rounded-t-3xl sm:rounded-2xl bg-card border-t sm:border border-border shadow-2xl animate-in fade-in slide-in-from-bottom-4 sm:zoom-in-95 duration-300">
                <div className="flex items-center justify-between px-5 pt-5 pb-3 bg-primary/5">
                    <h2 id="scan-title" className="font-semibold text-foreground text-lg flex items-center gap-2">
                        <ScanLine size={18} className="text-primary" />
                        {stage === 'review' ? 'Check the bill' : 'Scan a bill'}
                    </h2>
                    <button
                        type="button"
                        onClick={close}
                        aria-label="Close"
                        className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                    >
                        <X size={18} />
                    </button>
                </div>

                {stage === 'pick' && (
                    <div className="p-5 space-y-4">
                        <div
                            onDragOver={(event) => event.preventDefault()}
                            onDrop={onDrop}
                            className="rounded-2xl border-2 border-dashed border-border bg-muted/30 p-5 text-center"
                        >
                            <p className="text-sm text-foreground font-medium">A photo of a bill, or a PDF invoice</p>
                            <p className="mt-1 text-xs text-muted-foreground">
                                Groceries, pharmacy, restaurant, fuel… The shop, date, total and items are read for you.
                            </p>
                            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2">
                                <button
                                    type="button"
                                    onClick={() => cameraRef.current?.click()}
                                    className="flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 transition active:scale-95"
                                >
                                    <Camera size={16} /> Take a photo
                                </button>
                                <button
                                    type="button"
                                    onClick={() => uploadRef.current?.click()}
                                    className="flex items-center justify-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-semibold text-foreground hover:bg-muted transition"
                                >
                                    <FileUp size={16} /> Upload photo or PDF
                                </button>
                            </div>
                            <p className="mt-3 hidden sm:block text-[11px] text-muted-foreground">or drop a file here</p>
                            <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={onPick} />
                            <input ref={uploadRef} type="file" accept="image/*,application/pdf" className="hidden" onChange={onPick} />
                        </div>
                        {error && (
                            <p role="alert" className="flex items-start gap-2 rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">
                                <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" /> {error}
                            </p>
                        )}
                        <p className="text-[11px] text-muted-foreground leading-relaxed">
                            Tip: lay the bill flat in good light with all four edges in view. Nothing is saved until you
                            press Save; the bill is then kept privately with its transactions.
                        </p>
                    </div>
                )}

                {stage === 'reading' && (
                    <div className="p-6 flex flex-col items-center text-center gap-4">
                        {prepared?.previewUrl ? (
                            <img src={prepared.previewUrl} alt="The bill" className="max-h-48 rounded-xl border border-border object-contain" />
                        ) : (
                            <div className="flex h-24 w-20 items-center justify-center rounded-xl border border-border bg-muted">
                                <FileText size={28} className="text-muted-foreground" />
                            </div>
                        )}
                        <p className="flex items-center gap-2 text-sm font-medium text-foreground">
                            <Loader2 size={16} className="animate-spin text-primary" /> {reading}
                        </p>
                        {slow && (
                            <p className="text-xs text-muted-foreground max-w-xs">
                                The free server can take up to a minute when it has been asleep. Hang on…
                            </p>
                        )}
                        <button
                            type="button"
                            onClick={() => { abortRef.current?.abort(); setStage('pick'); }}
                            className="text-xs font-semibold text-muted-foreground hover:text-foreground"
                        >
                            Cancel
                        </button>
                    </div>
                )}

                {stage === 'review' && result && (
                    <div className="p-5 space-y-4">
                        <div className="flex gap-3">
                            {prepared?.previewUrl ? (
                                <img src={prepared.previewUrl} alt="The bill" className="h-28 w-20 flex-shrink-0 rounded-lg border border-border object-cover object-top" />
                            ) : (
                                <div className="flex h-28 w-20 flex-shrink-0 items-center justify-center rounded-lg border border-border bg-muted">
                                    <FileText size={22} className="text-muted-foreground" />
                                </div>
                            )}
                            <div className="flex-1 min-w-0 space-y-2">
                                <label className="block">
                                    <span className="text-xs font-medium text-muted-foreground">Shop</span>
                                    <input value={merchant} onChange={(e) => setMerchant(e.target.value)} placeholder="Shop name" className={inputClass} />
                                </label>
                                <div className="grid grid-cols-2 gap-2">
                                    <label className="block">
                                        <span className="text-xs font-medium text-muted-foreground">Date</span>
                                        <input type="date" value={date} max={todayISODate()} onChange={(e) => setDate(e.target.value)} className={inputClass} />
                                    </label>
                                    <label className="block">
                                        <span className="text-xs font-medium text-muted-foreground">Total (₹)</span>
                                        <input type="number" inputMode="decimal" min="0" step="0.01" value={total} onChange={(e) => setTotal(e.target.value)} className={inputClass} />
                                    </label>
                                </div>
                            </div>
                        </div>

                        {result.warnings.filter((key) => WARNINGS[key]).length > 0 && (
                            <ul className="space-y-1">
                                {result.warnings.filter((key) => WARNINGS[key]).map((key) => (
                                    <li key={key} className="flex items-start gap-2 rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-700">
                                        <AlertTriangle size={13} className="mt-0.5 flex-shrink-0" /> {WARNINGS[key]}
                                    </li>
                                ))}
                            </ul>
                        )}

                        {groups.length >= 2 && (
                            <div className="grid grid-cols-2 gap-1 rounded-xl bg-muted p-1 text-sm font-semibold" role="group" aria-label="How to save">
                                <button
                                    type="button"
                                    onClick={() => setSplit(true)}
                                    aria-pressed={split}
                                    className={`rounded-lg py-1.5 transition ${split ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground'}`}
                                >
                                    Split by category ({groups.length})
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setSplit(false)}
                                    aria-pressed={!split}
                                    className={`rounded-lg py-1.5 transition ${!split ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground'}`}
                                >
                                    One transaction
                                </button>
                            </div>
                        )}

                        {split ? (
                            <div className="space-y-2">
                                {groups.map((group, index) => (
                                    <div key={group.key} className={`rounded-xl border border-border p-3 ${group.include ? '' : 'opacity-50'}`}>
                                        <div className="flex items-center gap-2">
                                            <input
                                                type="checkbox"
                                                checked={group.include}
                                                onChange={(e) => updateGroup(index, { include: e.target.checked })}
                                                aria-label={`Include ${group.label}`}
                                                className="h-4 w-4 accent-primary"
                                            />
                                            <span className="text-sm font-semibold text-foreground flex-1 truncate">{group.label}</span>
                                            <input
                                                type="number"
                                                inputMode="decimal"
                                                min="0"
                                                step="0.01"
                                                value={group.amount}
                                                onChange={(e) => updateGroup(index, { amount: e.target.value })}
                                                aria-label={`Amount for ${group.label}`}
                                                className={`${fieldClass} w-28 flex-shrink-0 text-right tabular-nums`}
                                            />
                                        </div>
                                        <div className="mt-2 flex items-center gap-2">
                                            <div className="relative flex-1">
                                                <select
                                                    value={group.categoryId}
                                                    onChange={(e) => updateGroup(index, { categoryId: e.target.value })}
                                                    aria-label={`Category for ${group.label}`}
                                                    className={`${inputClass} appearance-none cursor-pointer pr-8`}
                                                >
                                                    {categoryOptions}
                                                </select>
                                                <ChevronDown size={14} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => setOpenGroup(openGroup === group.key ? null : group.key)}
                                                aria-expanded={openGroup === group.key}
                                                className="text-xs font-semibold text-primary whitespace-nowrap"
                                            >
                                                {group.items.length} item{group.items.length === 1 ? '' : 's'}
                                            </button>
                                        </div>
                                        {openGroup === group.key && (
                                            <ul className="mt-2 space-y-1 border-t border-border pt-2">
                                                {group.items.map((item, itemIndex) => (
                                                    <li key={`${item.name}-${itemIndex}`} className="flex justify-between gap-3 text-xs text-muted-foreground">
                                                        <span className="truncate">{item.name}</span>
                                                        <span className="tabular-nums">{money(item.amount)}</span>
                                                    </li>
                                                ))}
                                            </ul>
                                        )}
                                    </div>
                                ))}
                                <p className={`text-xs ${mismatch ? 'text-amber-700 font-medium' : 'text-muted-foreground'}`}>
                                    Groups add up to {money(groupsSum)} of {money(totalValue)}
                                    {result.adjustment ? ` (tax, discounts and rounding of ${money(result.adjustment)} are spread across them)` : ''}.
                                </p>
                            </div>
                        ) : (
                            <label className="block">
                                <span className="text-xs font-medium text-muted-foreground">Category</span>
                                <div className="relative">
                                    <select
                                        value={singleCategory}
                                        onChange={(e) => setSingleCategory(e.target.value)}
                                        className={`${inputClass} appearance-none cursor-pointer pr-8`}
                                    >
                                        {categoryOptions}
                                    </select>
                                    <ChevronDown size={14} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                                </div>
                            </label>
                        )}

                        {result.lines?.length > 0 && (
                            <div>
                                <button
                                    type="button"
                                    onClick={() => setShowText(!showText)}
                                    aria-expanded={showText}
                                    className="text-xs font-semibold text-muted-foreground hover:text-foreground"
                                >
                                    {showText ? 'Hide' : 'Show'} the text that was read
                                </button>
                                {showText && (
                                    <pre className="mt-2 max-h-40 overflow-auto rounded-xl bg-muted p-3 text-[11px] leading-relaxed text-muted-foreground whitespace-pre-wrap">
                                        {result.lines.join('\n')}
                                    </pre>
                                )}
                            </div>
                        )}

                        <div className="flex gap-2 pt-1">
                            <button
                                type="button"
                                onClick={reset}
                                disabled={saving}
                                className="flex-1 rounded-xl border border-border py-2.5 text-sm font-semibold text-foreground hover:bg-muted transition disabled:opacity-50"
                            >
                                Scan another
                            </button>
                            <button
                                type="button"
                                onClick={handleSave}
                                disabled={!canSave}
                                className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 transition disabled:opacity-50"
                            >
                                {saving && <Loader2 size={15} className="animate-spin" />}
                                {split ? `Save ${included.length} transaction${included.length === 1 ? '' : 's'}` : 'Save'}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>,
        document.body
    );
};

export default ReceiptScanModal;
