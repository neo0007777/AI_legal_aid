import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import hi from './locales/hi.json';
import mr from './locales/mr.json';
import bn from './locales/bn.json';
import ta from './locales/ta.json';
import te from './locales/te.json';
import kn from './locales/kn.json';
import gu from './locales/gu.json';
import ml from './locales/ml.json';
import pa from './locales/pa.json';
import or_ from './locales/or.json';

// Static UI chrome (menus, buttons, labels) is pre-translated and shipped as
// JSON, never LLM-translated at runtime -- runtime LLM translation is
// reserved for dynamic legal content (see translate_output.py / TranslateAction).
// Every language in LanguageContext.SUPPORTED_LANGUAGES has a matching entry
// here; any key missing from a translation file still falls back to English
// via i18next's fallbackLng rather than rendering blank.
const resources = {
    en: { translation: en },
    hi: { translation: hi },
    mr: { translation: mr },
    bn: { translation: bn },
    ta: { translation: ta },
    te: { translation: te },
    kn: { translation: kn },
    gu: { translation: gu },
    ml: { translation: ml },
    pa: { translation: pa },
    or: { translation: or_ },
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
