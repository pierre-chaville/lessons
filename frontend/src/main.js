import { createApp, watch } from 'vue';
import { clerkPlugin, updateClerkOptions } from '@clerk/vue';
import { enUS, frFR } from '@clerk/localizations';
import App from './App.vue';
import i18n from './i18n';
import './assets/styles/main.css';

const app = createApp(App);

const resolveClerkLocalization = (localeValue) => {
  if (localeValue === 'en') return enUS;
  return frFR;
};

app.use(i18n);
app.use(clerkPlugin, {
  publishableKey: import.meta.env.VITE_CLERK_PUBLISHABLE_KEY,
  localization: resolveClerkLocalization(i18n.global.locale.value)
});

watch(i18n.global.locale, (newLocale) => {
  updateClerkOptions({
    localization: resolveClerkLocalization(newLocale)
  });
});

app.mount('#app');

