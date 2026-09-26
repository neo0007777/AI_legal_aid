/**
 * Robust file downloader for client-side blob downloads.
 * Fixes premature ObjectURL revocation bug where browsers fail or download 0-byte corrupt files.
 */
export const downloadFileFromBlob = (blob, filename, mimeType = 'application/pdf') => {
    try {
        if (!blob) {
            throw new Error('No file data provided for download.');
        }

        // If it's already a Blob, use it directly or ensure correct mime type
        let fileBlob;
        if (blob instanceof Blob) {
            fileBlob = blob.type ? blob : new Blob([blob], { type: mimeType });
        } else {
            fileBlob = new Blob([blob], { type: mimeType });
        }

        if (fileBlob.size === 0) {
            throw new Error('Downloaded document is empty (0 bytes).');
        }

        // Ensure correct extension
        let safeFilename = filename;
        if (mimeType.includes('pdf') && !safeFilename.toLowerCase().endsWith('.pdf')) {
            safeFilename += '.pdf';
        } else if (mimeType.includes('text') && !safeFilename.toLowerCase().endsWith('.txt')) {
            safeFilename += '.txt';
        } else if (mimeType.includes('csv') && !safeFilename.toLowerCase().endsWith('.csv')) {
            safeFilename += '.csv';
        }

        const url = window.URL.createObjectURL(fileBlob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = safeFilename;
        a.setAttribute('download', safeFilename);
        document.body.appendChild(a);
        a.click();

        // Delay revocation by 4 seconds so Chromium/WebKit can safely stream to disk
        setTimeout(() => {
            try {
                if (a.parentNode) {
                    a.parentNode.removeChild(a);
                }
                window.URL.revokeObjectURL(url);
            } catch (cleanupErr) {
                console.warn('ObjectURL cleanup warning:', cleanupErr);
            }
        }, 4000);
    } catch (err) {
        console.error('Download error:', err);
        throw err;
    }
};

/**
 * Universal helper to call a PDF export endpoint and trigger browser download.
 */
export const exportPdfFromApi = async ({
    endpoint,
    body,
    filename,
    headers = {},
}) => {
    const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...headers,
        },
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        let errorDetail = `Server error (${response.status})`;
        try {
            const errJson = await response.json();
            errorDetail = errJson.detail || errorDetail;
        } catch {
            // text or html error
        }
        throw new Error(errorDetail);
    }

    const blob = await response.blob();
    downloadFileFromBlob(blob, filename, 'application/pdf');
};
