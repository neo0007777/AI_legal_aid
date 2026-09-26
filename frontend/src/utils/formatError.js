/**
 * Universal error formatter for API responses.
 * Guarantees a safe string output so React never crashes with:
 * "Objects are not valid as a React child (found: object with keys {type, loc, msg, input, ctx})"
 */
export const formatErrorMessage = (error, fallback = 'An unexpected error occurred.') => {
    if (!error) return fallback;
    if (typeof error === 'string') return error;

    // Handle Pydantic / FastAPI 422 validation error arrays
    if (Array.isArray(error)) {
        const messages = error
            .map(item => {
                if (typeof item === 'string') return item;
                if (item && typeof item === 'object') {
                    const field = Array.isArray(item.loc) && item.loc.length > 0
                        ? item.loc[item.loc.length - 1]
                        : null;
                    const msg = item.msg || item.message || JSON.stringify(item);
                    return field && field !== 'body' ? `${field}: ${msg}` : msg;
                }
                return String(item);
            })
            .filter(Boolean);

        return messages.length > 0 ? messages.join('; ') : fallback;
    }

    // Handle single error objects
    if (typeof error === 'object') {
        if (error.detail) return formatErrorMessage(error.detail, fallback);
        if (error.message) return formatErrorMessage(error.message, fallback);
        if (error.msg) return error.msg;
        try {
            return JSON.stringify(error);
        } catch {
            return fallback;
        }
    }

    return String(error);
};
