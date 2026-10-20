/**
 * Get a bill ready to send: photos are turned upright (the camera's EXIF tag), shrunk so the
 * long side is at most 2,000 px and re-encoded as JPEG, which also converts iPhone HEIC photos
 * where the browser can decode them. A 6 MB phone photo becomes about 400 KB, so it uploads
 * quickly and the server reads it faster. PDFs are sent as they are.
 */

export const MAX_PDF_BYTES = 8 * 1024 * 1024;
const MAX_SIDE = 2000;

const isPdf = (file) => file.type === 'application/pdf' || /\.pdf$/i.test(file.name || '');

/**
 * @param {File} file
 * @returns {Promise<{ file: File, kind: 'image'|'pdf', previewUrl: string|null }>}
 */
export async function prepareReceiptFile(file) {
    if (isPdf(file)) {
        if (file.size > MAX_PDF_BYTES) throw new Error('That PDF is too large: 8 MB at most.');
        return { file, kind: 'pdf', previewUrl: null };
    }
    if (!file.type.startsWith('image/') && !/\.(heic|heif)$/i.test(file.name || '')) {
        throw new Error('Choose a photo or a PDF of the bill.');
    }

    let bitmap;
    try {
        bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
    } catch {
        throw new Error("This photo's format can't be read here. Take a new photo, or save it as a JPEG.");
    }
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close?.();

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85));
    if (!blob) throw new Error('Could not prepare the photo. Please try another one.');
    const jpeg = new File([blob], 'bill.jpg', { type: 'image/jpeg' });
    return { file: jpeg, kind: 'image', previewUrl: URL.createObjectURL(jpeg) };
}
