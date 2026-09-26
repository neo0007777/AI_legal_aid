import React, { createContext, useContext, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

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
const STORAGE_KEY = 'lexsetu_language';

export const SUPPORTED_LANGUAGES = [
    { code: 'en', label: 'English', nativeLabel: 'English', i18nCode: 'en' },
];

export const LanguageProvider = ({ children }) => {
    const { i18n } = useTranslation();

    useEffect(() => {
        try {
            localStorage.removeItem(STORAGE_KEY);
        } catch { /* ignore */ }
        i18n.changeLanguage('en');
    }, [i18n]);

    const value = {
        languageCode: 'en',
        setLanguage: () => {},
        currentLanguage: SUPPORTED_LANGUAGES[0],
        languages: SUPPORTED_LANGUAGES,
    };

    return (
        <LanguageContext.Provider value={value}>
            {children}
        </LanguageContext.Provider>
    );
};
