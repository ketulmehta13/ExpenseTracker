import React, { useState, useEffect } from 'react';
import { Plus, X, Pencil, Trash2, Filter, Download, FileText } from 'lucide-react';
import { getTransactions, createTransaction, updateTransaction, deleteTransaction, exportTransactionsCSV } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import UnusualSpendingBadge from '../components/UnusualSpendingBadge';
import { jsPDF } from 'jspdf';
import 'jspdf-autotable';

const Transactions = () => {
    const { user } = useAuth();
    const [transactions, setTransactions] = useState([]);
    const [loading, setLoading] = useState(true);
    
    // Filters
    const [filterType, setFilterType] = useState('');
    
    // Modal state
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingTransaction, setEditingTransaction] = useState(null);
    const [formData, setFormData] = useState({
        title: '',
        amount: '',
        type: 'EXPENSE',
        date: new Date().toISOString().split('T')[0],
        notes: '',
        is_recurring: false
    });

    useEffect(() => {
        fetchData();
    }, [filterType]);

    const fetchData = async () => {
        setLoading(true);
        try {
            const data = await getTransactions(filterType);
            setTransactions(data);
        } catch (error) {
            console.error('Error fetching data', error);
        } finally {
            setLoading(false);
        }
    };

    const handleExportCSV = () => {
        exportTransactionsCSV(transactions);
    };

    const handleExportPDF = () => {
        const doc = new jsPDF();
        
        // Add Title
        doc.setFontSize(20);
        doc.setTextColor(13, 58, 53); // Dark teal color from theme
        doc.text('Expense Tracker - Transactions Report', 14, 22);
        
        doc.setFontSize(10);
        doc.setTextColor(100);
        doc.text(`Generated on: ${new Date().toLocaleString()}`, 14, 30);
        doc.text(`User: Authenticated User`, 14, 35);

        // Prepare table data
        const tableColumn = ["Date", "Title", "Type", "Amount"];
        const tableRows = transactions.map(t => [
            new Date(t.date).toLocaleDateString(),
            t.title,
            t.type,
            `${t.type === 'INCOME' ? '+' : '-'}₹${parseFloat(t.amount).toFixed(2)}`
        ]);

        // Add table
        doc.autoTable({
            head: [tableColumn],
            body: tableRows,
            startY: 45,
            theme: 'striped',
            headStyles: { fillColor: [13, 58, 53], textColor: [255, 255, 255] },
            alternateRowStyles: { fillColor: [241, 245, 244] },
            margin: { top: 45 },
            styles: { fontSize: 9, cellPadding: 3 }
        });

        // Add summary footer
        const finalY = doc.lastAutoTable.finalY + 10;
        const totalIncome = transactions.filter(t => t.type === 'INCOME').reduce((sum, t) => sum + parseFloat(t.amount), 0);
        const totalExpense = transactions.filter(t => t.type === 'EXPENSE').reduce((sum, t) => sum + parseFloat(t.amount), 0);
        
        doc.setFontSize(12);
        doc.setTextColor(0);
        doc.text(`Total Income: ₹${totalIncome.toFixed(2)}`, 14, finalY);
        doc.text(`Total Expense: ₹${totalExpense.toFixed(2)}`, 14, finalY + 7);
        doc.setFontSize(14);
        doc.text(`Net Balance: ₹${(totalIncome - totalExpense).toFixed(2)}`, 14, finalY + 16);

        doc.save('transactions_report.pdf');
    };

    const handleDelete = async (id) => {
        if (confirm('Are you sure you want to delete this transaction?')) {
            try {
                await deleteTransaction(id);
                fetchData();
            } catch (error) {
                console.error('Failed to delete', error);
            }
        }
    };

    const handleOpenModal = (transaction = null) => {
        if (transaction) {
            setEditingTransaction(transaction);
            setFormData({
                title: transaction.title,
                amount: transaction.amount,
                type: transaction.type,
                date: transaction.date,
                notes: transaction.notes || '',
                is_recurring: transaction.is_recurring || false
            });
        } else {
            setEditingTransaction(null);
            setFormData({
                title: '',
                amount: '',
                type: 'EXPENSE',
                date: new Date().toISOString().split('T')[0],
                notes: '',
                is_recurring: false
            });
        }
        setIsModalOpen(true);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            if (editingTransaction) {
                await updateTransaction(editingTransaction.id, formData);
            } else {
                await createTransaction(user.id, formData);
            }
            setIsModalOpen(false);
            fetchData();
        } catch (error) {
            console.error('Failed to save transaction', error);
            alert('Error saving transaction. Check your inputs.');
        }
    };

    // Auto-categorize removal - no longer needed as categories are hidden
    useEffect(() => {
        // Categories are disabled
    }, []);

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div className="flex flex-col gap-1">
                    <h1 className="text-3xl font-bold tracking-tight">Transactions</h1>
                    <p className="text-muted-foreground">Manage your past and recurring transactions.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
                    <Button variant="outline" size="sm" onClick={handleExportCSV}>
                        <Download className="mr-2 h-4 w-4" /> CSV
                    </Button>
                    <Button variant="outline" size="sm" onClick={handleExportPDF}>
                        <FileText className="mr-2 h-4 w-4" /> PDF
                    </Button>
                    <Button size="sm" onClick={() => handleOpenModal()}>
                        <Plus className="mr-2 h-4 w-4" /> Add New
                    </Button>
                </div>
            </div>

            {/* Filters */}
            <Card>
                <CardContent className="p-4 flex flex-col sm:flex-row gap-4 items-center">
                    <div className="flex items-center text-muted-foreground">
                        <Filter className="h-5 w-5 mr-2" />
                        <span className="font-medium mr-4">Filters</span>
                    </div>
                    
                    <select 
                        value={filterType} 
                        onChange={(e) => setFilterType(e.target.value)}
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 sm:w-[150px]"
                    >
                        <option value="">All Types</option>
                        <option value="INCOME">Income</option>
                        <option value="EXPENSE">Expense</option>
                    </select>

                    <Button 
                        variant="ghost"
                        onClick={() => { setFilterType(''); }}
                    >
                        Clear
                    </Button>
                </CardContent>
            </Card>

            {/* Transactions List */}
            <Card className="overflow-hidden">
                {loading ? (
                    <div className="p-12 text-center text-muted-foreground">Loading transactions...</div>
                ) : transactions.length === 0 ? (
                    <div className="p-12 text-center text-muted-foreground">
                        No transactions found. Start tracking your expenses!
                    </div>
                ) : (
                    <div className="overflow-x-auto relative">
                        <table className="w-full text-sm text-left">
                            <thead className="text-xs text-muted-foreground uppercase bg-secondary/50 border-b">
                                <tr>
                                    <th className="px-6 py-4 font-semibold">Date</th>
                                    <th className="px-6 py-4 font-semibold">Title</th>
                                    <th className="px-6 py-4 font-semibold">Amount</th>
                                    <th className="px-6 py-4 font-semibold text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border/50">
                                {transactions.map((t) => (
                                    <tr key={t.id} className="hover:bg-muted/50 transition-colors">
                                        <td className="px-6 py-4 text-muted-foreground">{new Date(t.date).toLocaleDateString()}</td>
                                        <td className="px-6 py-4 font-medium">
                                            {t.title}
                                            {t.is_recurring && (
                                                <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
                                                    Recurring
                                                </span>
                                            )}
                                            {t.spending_insight?.is_unusual && (
                                                <span className="ml-2">
                                                    <UnusualSpendingBadge />
                                                </span>
                                            )}
                                        </td>
                                        <td className={`px-6 py-4 font-bold ${t.type === 'INCOME' ? 'text-emerald-500' : 'text-destructive'}`}>
                                            {t.type === 'INCOME' ? '+' : '-'}₹{parseFloat(t.amount).toFixed(2)}
                                        </td>
                                        <td className="px-6 py-4 text-right flex justify-end space-x-1">
                                            <Button variant="ghost" size="icon" onClick={() => handleOpenModal(t)}>
                                                <Pencil className="h-4 w-4" />
                                            </Button>
                                            <Button variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10" onClick={() => handleDelete(t.id)}>
                                                <Trash2 className="h-4 w-4" />
                                            </Button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>

            {/* Modal */}
            {isModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in">
                    <Card className="w-full max-w-md shadow-lg border-border">
                        <CardHeader className="flex flex-row items-center justify-between pb-4">
                            <CardTitle>
                                {editingTransaction ? 'Edit Transaction' : 'Add Transaction'}
                            </CardTitle>
                            <Button variant="ghost" size="icon" className="h-8 w-8 rounded-full" onClick={() => setIsModalOpen(false)}>
                                <X className="h-4 w-4" />
                            </Button>
                        </CardHeader>
                        <CardContent>
                            <form onSubmit={handleSubmit} className="space-y-4">
                                <div className="space-y-2">
                                    <Label>Type</Label>
                                    <div className="flex p-1 bg-secondary rounded-lg">
                                        <button
                                            type="button"
                                            className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-all ${formData.type === 'EXPENSE' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`}
                                            onClick={() => setFormData({...formData, type: 'EXPENSE'})}
                                        >
                                            Expense
                                        </button>
                                        <button
                                            type="button"
                                            className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-all ${formData.type === 'INCOME' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`}
                                            onClick={() => setFormData({...formData, type: 'INCOME'})}
                                        >
                                            Income
                                        </button>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="title">Title</Label>
                                    <Input 
                                        id="title"
                                        required
                                        value={formData.title}
                                        onChange={(e) => setFormData({...formData, title: e.target.value})}
                                        placeholder="e.g. Groceries"
                                    />
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="amount">Amount</Label>
                                        <Input 
                                            id="amount"
                                            type="number" 
                                            step="0.01"
                                            required
                                            value={formData.amount}
                                            onChange={(e) => setFormData({...formData, amount: e.target.value})}
                                            placeholder="0.00"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="date">Date</Label>
                                        <Input 
                                            id="date"
                                            type="date" 
                                            required
                                            value={formData.date}
                                            onChange={(e) => setFormData({...formData, date: e.target.value})}
                                        />
                                    </div>
                                </div>


                                
                                <div className="space-y-2">
                                    <Label htmlFor="notes">Notes (Optional)</Label>
                                    <Input 
                                        id="notes"
                                        type="text"
                                        value={formData.notes}
                                        onChange={(e) => setFormData({...formData, notes: e.target.value})}
                                        placeholder="Add a note"
                                    />
                                </div>
                                
                                <div className="flex items-center space-x-2 pt-2 pb-2">
                                    <input 
                                        type="checkbox"
                                        id="is_recurring"
                                        checked={formData.is_recurring}
                                        onChange={(e) => setFormData({...formData, is_recurring: e.target.checked})}
                                        className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                                    />
                                    <Label htmlFor="is_recurring" className="font-normal cursor-pointer">
                                        Mark as recurring transaction
                                    </Label>
                                </div>

                                <div className="pt-2 flex justify-end gap-3">
                                    <Button type="button" variant="outline" onClick={() => setIsModalOpen(false)}>
                                        Cancel
                                    </Button>
                                    <Button type="submit">
                                        {editingTransaction ? 'Update' : 'Save'}
                                    </Button>
                                </div>
                            </form>
                        </CardContent>
                    </Card>
                </div>
            )}
        </div>
    );
};

export default Transactions;
