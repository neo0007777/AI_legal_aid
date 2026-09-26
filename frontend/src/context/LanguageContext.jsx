import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from './AuthContext';

const LanguageContext = createContext();
export const useLanguage = () => useContext(LanguageContext);

// App-wide language preference (generalizes the Hindi-only "regional-language
// grounded mode" into a curated Eighth-Schedule-first language list). This is
// a RENDERING preference only -- see translate_output.py for the correctness
// rule it must never violate: retrieval/verification always run in English,
// language selection happens strictly after generation is complete.
//
// Adding a language later is a data change to this list (+ a locale JSON file
// for static UI strings), not a rewrite -- nothing else hardcodes "Hindi".
export const SUPPORTED_LANGUAGES = [
    { code: 'en', label: 'English', nativeLabel: 'English', i18nCode: 'en' },
    { code: 'hindi', label: 'Hindi', nativeLabel: 'हिन्दी', i18nCode: 'hi' },
    { code: 'marathi', label: 'Marathi', nativeLabel: 'मराठी', i18nCode: 'mr' },
    { code: 'bengali', label: 'Bengali', nativeLabel: 'বাংলা', i18nCode: 'bn' },
    { code: 'tamil', label: 'Tamil', nativeLabel: 'தமிழ்', i18nCode: 'ta' },
    { code: 'telugu', label: 'Telugu', nativeLabel: 'తెలుగు', i18nCode: 'te' },
    { code: 'kannada', label: 'Kannada', nativeLabel: 'ಕನ್ನಡ', i18nCode: 'kn' },
    { code: 'gujarati', label: 'Gujarati', nativeLabel: 'ગુજરાતી', i18nCode: 'gu' },
    { code: 'malayalam', label: 'Malayalam', nativeLabel: 'മലയാളം', i18nCode: 'ml' },
    { code: 'punjabi', label: 'Punjabi', nativeLabel: 'ਪੰਜਾਬੀ', i18nCode: 'pa' },
    { code: 'odia', label: 'Odia', nativeLabel: 'ଓଡ଼ିଆ', i18nCode: 'or' },
];

const STORAGE_KEY = 'lexsetu_language';

export const LanguageProvider = ({ children }) => {
    const { i18n } = useTranslation();
    const { user, getAuthHeaders, isAuthenticated } = useAuth() || {};

    const [languageCode, setLanguageCodeState] = useState(() => {
        try {
            return localStorage.getItem(STORAGE_KEY) || 'en';
        } catch {
            return 'en';
        }
    });

    // Static UI chrome only understands i18n codes we actually ship
    // (en, hi) -- everything else keeps the English UI chrome (scope cut:
    // an honest partial i18n state, not a broken "translate everything"
    // promise) while dynamic legal-content translation still works for the
    // full curated list.
    useEffect(() => {
        const entry = SUPPORTED_LANGUAGES.find(l => l.code === languageCode);
        i18n.changeLanguage(entry?.i18nCode || 'en');
    }, [languageCode, i18n]);

    useEffect(() => {
        try {
            localStorage.setItem(STORAGE_KEY, languageCode);
        } catch { /* ignore */ }
    }, [languageCode]);

    // Best-effort sync with the logged-in user's saved preference: on login,
    // adopt their stored profile preference; on change, push it back. Never
    // blocks the UI on failure -- localStorage remains the source of truth
    // for this session either way.
    useEffect(() => {
        if (!isAuthenticated || !user) return;
        (async () => {
            try {
                const res = await fetch('/api/auth/me', { headers: getAuthHeaders() });
                if (res.ok) {
                    const data = await res.json();
                    if (data.preferred_language && data.preferred_language !== languageCode) {
                        setLanguageCodeState(data.preferred_language);
                    }
                }
            } catch { /* offline/local-only -- keep localStorage value */ }
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isAuthenticated, user?.id]);

    const setLanguage = useCallback((code) => {
        if (!SUPPORTED_LANGUAGES.some(l => l.code === code)) return;
        setLanguageCodeState(code);
        if (isAuthenticated) {
            fetch('/api/auth/me/language', {
                method: 'PATCH',
                headers: getAuthHeaders(),
                body: JSON.stringify({ preferred_language: code }),
            }).catch(() => { /* best-effort only */ });
        }
    }, [isAuthenticated, getAuthHeaders]);

    const currentLanguage = SUPPORTED_LANGUAGES.find(l => l.code === languageCode) || SUPPORTED_LANGUAGES[0];

    return (
        <LanguageContext.Provider value={{ languageCode, setLanguage, currentLanguage, languages: SUPPORTED_LANGUAGES }}>
            {children}
        </LanguageContext.Provider>
    );
};
