import { toast } from 'sonner';
import { getReceiptUrl } from '../services/api';

/** Open the bill scanner from anywhere: MainLayout hosts it and listens for this event. */
export const openReceiptScanner = () => window.dispatchEvent(new CustomEvent('open-receipt-scan'));

/**
 * Show a stored bill in a new tab through a link that works for a minute. The tab is opened
 * before the link is fetched, inside the click, so pop-up blockers allow it.
 */
export async function openReceipt(path) {
    const tab = window.open('', '_blank');
    try {
        const url = await getReceiptUrl(path);
        if (tab) {
            tab.opener = null;
            tab.location.href = url;
        } else {
            window.location.assign(url);
        }
    } catch {
        tab?.close();
        toast.error('Could not open the bill. Please try again.');
    }
}
