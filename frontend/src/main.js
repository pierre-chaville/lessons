import { createApp } from 'vue';
import { clerkPlugin } from '@clerk/vue';
import App from './App.vue';
import i18n from './i18n';
import './assets/styles/main.css';

const app = createApp(App);

app.use(i18n);
app.use(clerkPlugin, {
  publishableKey: import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
});

app.mount('#app');

