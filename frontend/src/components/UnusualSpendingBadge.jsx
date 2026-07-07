import React from 'react';
import { AlertTriangle } from 'lucide-react';

const UnusualSpendingBadge = () => {
    return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400 border border-rose-200 dark:border-rose-800" title="This transaction is unusually high compared to your past spending in this category">
            <AlertTriangle className="w-3 h-3" />
            Unusual spending
        </span>
    );
};

export default UnusualSpendingBadge;
