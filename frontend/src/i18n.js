import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import hi from './locales/hi.json';

// Static UI chrome (menus, buttons, labels) is pre-translated and shipped as
// JSON, never LLM-translated at runtime -- runtime LLM translation is
// reserved for dynamic legal content (see translate_output.py / TranslateAction).
// Only en + hi are fully translated for v1; every other supported language
// (see LanguageContext.SUPPORTED_LANGUAGES) falls back to English for any
// missing key via i18next's fallbackLng, rather than blocking the switcher.
const resources = {
    en: { translation: en },
    hi: { translation: hi },
};

i18n
    .use(initReactI18next)
    .init({
        resources,
        lng: 'en',
        fallbackLng: 'en',
        interpolation: { escapeValue: false },
        returnEmptyString: false,
    });

export default i18n;
