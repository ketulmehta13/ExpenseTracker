import { formatDate } from './formatters';

// jsPDF's built-in fonts can't draw symbols like ₹, so amounts use the currency
// code instead ("INR 1,250.00").
const formatAmountForPdf = (amount, currency) =>
    new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency,
        currencyDisplay: 'code',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })
        .format(Number(amount))
        .replace(/\xa0/g, ' ');

/**
 * Download a PDF report of the given transactions.
 * jsPDF is loaded on demand so it stays out of the main bundle.
 */
export const exportTransactionsPDF = async (transactions) => {
    const [{ jsPDF }, { autoTable }] = await Promise.all([
        import('jspdf'),
        import('jspdf-autotable'),
    ]);
    const currency = localStorage.getItem('et-currency') || 'INR';

    const doc = new jsPDF();
    doc.setFontSize(16);
    doc.text('Expense Tracker - Transactions Report', 14, 20);
    doc.setFontSize(9);
    doc.setTextColor(120);
    doc.text(`Generated: ${new Date().toLocaleString('en-IN')}`, 14, 28);

    autoTable(doc, {
        head: [['Date', 'Title', 'Category', 'Type', 'Amount']],
        body: transactions.map((t) => [
            formatDate(t.date),
            t.title,
            t.category_name || '-',
            t.type,
            `${t.type === 'INCOME' ? '+' : '-'}${formatAmountForPdf(t.amount, currency)}`,
        ]),
        startY: 34,
        theme: 'striped',
        headStyles: { fillColor: [34, 40, 58] },
        styles: { fontSize: 8, cellPadding: 3 },
        columnStyles: { 4: { halign: 'right' } },
    });

    doc.save('transactions_report.pdf');
};
