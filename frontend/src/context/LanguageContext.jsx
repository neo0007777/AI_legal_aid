import React, { createContext, useContext, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

const LanguageContext = createContext();
export const useLanguage = () => useContext(LanguageContext);

export const SUPPORTED_LANGUAGES = [
    { code: 'en', label: 'English',    nativeLabel: 'English',    i18nCode: 'en' },
    { code: 'hi', label: 'Hindi',      nativeLabel: 'हिन्दी',      i18nCode: 'hi' },
    { code: 'mr', label: 'Marathi',    nativeLabel: 'मराठी',       i18nCode: 'mr' },
    { code: 'bn', label: 'Bengali',    nativeLabel: 'বাংলা',       i18nCode: 'bn' },
    { code: 'ta', label: 'Tamil',      nativeLabel: 'தமிழ்',       i18nCode: 'ta' },
    { code: 'te', label: 'Telugu',     nativeLabel: 'తెలుగు',      i18nCode: 'te' },
    { code: 'kn', label: 'Kannada',    nativeLabel: 'ಕನ್ನಡ',       i18nCode: 'kn' },
    { code: 'gu', label: 'Gujarati',   nativeLabel: 'ગુજરાતી',     i18nCode: 'gu' },
    { code: 'ml', label: 'Malayalam',  nativeLabel: 'മലയാളം',      i18nCode: 'ml' },
    { code: 'pa', label: 'Punjabi',    nativeLabel: 'ਪੰਜਾਬੀ',      i18nCode: 'pa' },
    { code: 'or', label: 'Odia',       nativeLabel: 'ଓଡ଼ିଆ',       i18nCode: 'or' },
];

const STORAGE_KEY = 'lexsetu_language';

export const LanguageProvider = ({ children }) => {
    const { i18n } = useTranslation();

    const [languageCode, setLanguageCode] = useState(() => {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved && SUPPORTED_LANGUAGES.some(l => l.code === saved)) return saved;
        } catch { /* ignore */ }
        return 'en';
    });

    useEffect(() => {
        i18n.changeLanguage(languageCode);
    }, [languageCode, i18n]);

    const setLanguage = (code) => {
        if (!SUPPORTED_LANGUAGES.some(l => l.code === code)) return;
        setLanguageCode(code);
        try { localStorage.setItem(STORAGE_KEY, code); } catch { /* ignore */ }
    };

    const currentLanguage = SUPPORTED_LANGUAGES.find(l => l.code === languageCode) || SUPPORTED_LANGUAGES[0];

    const value = {
        languageCode,
        setLanguage,
        currentLanguage,
        languages: SUPPORTED_LANGUAGES,
    };

    return (
        <LanguageContext.Provider value={value}>
            {children}
        </LanguageContext.Provider>
    );
};

