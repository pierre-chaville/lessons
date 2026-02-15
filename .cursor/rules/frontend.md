# Frontend Cursor Rules — Torah Lessons Transcription Platform

## Project Overview

Vue.js SPA for a Torah lessons transcription platform. Users browse, read, and manage transcribed Torah lessons, edited long-form versions, Sefaria source references, and summaries. Invitation-only, role-based access via Clerk. The frontend communicates with a FastAPI backend API.

## Tech Stack

- **Framework**: Vue 3 (Composition API + `<script setup>`)
- **Routing**: Vue Router 4
- **Styling**: Tailwind CSS 3
- **UI Components**: Headless UI (Vue)
- **Auth**: Clerk (Vue SDK — `@clerk/vue`)
- **i18n**: Vue I18n 9 (French + English)
- **HTTP Client**: Axios (with auth interceptor)
- **Build**: Vite
- **Hosting**: Render.com (static site) or Cloudflare Pages
- **Language**: TypeScript (incremental migration from JavaScript)

## TypeScript Migration Strategy

The project is migrating from plain JavaScript to TypeScript incrementally. Both `.js` and `.ts` files coexist during the transition.

**Rules for new code:**
- All new files must be `.ts` or `.vue` with `<script setup lang="ts">`.
- All new composables, API modules, and utilities must be fully typed.
- New components must type their props with `defineProps<{...}>()` and emits with `defineEmits<{...}>()`.

**Rules for existing code:**
- When modifying an existing `.js` file, convert it to `.ts` in the same PR if the change is non-trivial.
- Don't convert files you're not otherwise touching — avoid large "convert everything" PRs.
- Start with the highest-value files: `api/` layer, composables, types, then components.

**tsconfig.json:**
- Enable `strict: true` for new code.
- Use `allowJs: true` to permit mixed JS/TS during migration.
- Set `"paths": { "@/*": ["./src/*"] }` for clean imports.

## Project Structure

```
src/
├── App.vue
├── main.ts                      # App init, plugins (Clerk, router)
├── router/
│   └── index.ts                 # Route definitions with meta.requiredRole
├── api/                         # Backend API client layer
│   ├── client.ts                # Base fetch wrapper with auth headers
│   ├── lessons.ts               # Lesson CRUD functions
│   ├── tasks.ts                 # Task endpoints
│   ├── courses.ts
│   ├── sources.ts
│   └── types.ts                 # API response/request TypeScript types
├── i18n/                        # Internationalization
│   ├── index.ts                 # i18n instance setup
│   └── locales/
│       ├── fr.json              # French translations (primary)
│       └── en.json              # English translations
├── composables/                 # Reusable Composition API logic
│   ├── usePermissions.ts        # Role-based permission checks (see access.md)
│   ├── useAuth.ts               # Clerk auth state wrapper
│   ├── usePagination.ts
│   ├── useTask.ts               # Task polling / status tracking
│   └── useToast.ts              # Notification system
├── components/
│   ├── ui/                      # Generic reusable components (buttons, modals, dropdowns)
│   ├── lessons/                 # Lesson-specific components
│   ├── courses/
│   ├── sources/
│   ├── tasks/
│   └── layout/                  # Shell, sidebar, header, navigation
├── views/                       # Route-level page components
│   ├── LessonsListView.vue
│   ├── LessonDetailView.vue
│   ├── LessonEditView.vue
│   ├── CoursesListView.vue
│   ├── TasksView.vue            # Publisher/admin only
│   ├── ConfigurationView.vue    # Publisher (read) / admin (write)
│   └── NotFoundView.vue
├── stores/                      # Pinia stores (if needed for shared state)
├── utils/                       # Pure helper functions
│   ├── format.ts                # Date, text formatting
│   └── sefaria.ts               # Sefaria reference formatting/linking
├── types/                       # Shared TypeScript types/interfaces
│   └── index.ts
├── assets/
│   └── styles/
│       └── main.css             # Tailwind directives + custom base styles
└── scripts/                     # Dev utility scripts
```

## Code Style & Conventions

### General

- **Always use `<script setup lang="ts">`** — no Options API, no `defineComponent()`.
- All code, comments, and variable names in **English**.
- **All user-facing text must go through `$t()` / `t()`** — never hardcode French or English strings in templates or scripts. See the Internationalization section below.
- Use TypeScript strict mode. Type all props, emits, composable return values, and API responses.
- Prefer `const` over `let`. Never use `var`.

### Component File Structure

Follow this order inside every `.vue` file:

```vue
<script setup lang="ts">
// 1. Imports
// 2. Props & emits
// 3. Composables (useAuth, usePermissions, etc.)
// 4. Reactive state (ref, reactive, computed)
// 5. Functions
// 6. Lifecycle hooks (onMounted, watch, etc.)
</script>

<template>
  <!-- Single root element preferred but not required (Vue 3 fragments OK) -->
</template>

<style scoped>
/* Only when Tailwind classes are insufficient */
</style>
```

### Naming

- Components: `PascalCase.vue` — e.g. `LessonCard.vue`, `TaskStatusBadge.vue`
- Composables: `useCamelCase.ts` — e.g. `usePermissions.ts`, `useTask.ts`
- Views (route pages): `PascalCaseView.vue` — e.g. `LessonDetailView.vue`
- API modules: `camelCase.ts` — e.g. `lessons.ts`, `tasks.ts`
- Utility files: `camelCase.ts`
- TypeScript types/interfaces: `PascalCase` — e.g. `Lesson`, `TaskStatus`
- Props: `camelCase` in script, `kebab-case` in template
- Events: `camelCase` with `emit('updateLesson', ...)`, not `emit('update-lesson', ...)`
- CSS classes: Tailwind utilities only — no custom class names unless absolutely necessary

### Component Design Principles

- **Keep components small and focused** — one responsibility per component.
- **Props down, events up** — children never mutate parent state directly.
- **Composables for shared logic** — don't duplicate reactive logic across components.
- **Views are thin** — they compose components and connect to the API layer. Minimal logic in views.
- **No business logic in templates** — complex conditions should be computed properties.

## TypeScript

### Types for API Responses

```typescript
// api/types.ts
export interface Lesson {
  id: string
  title: string
  rabbi: string | null
  status: 'draft' | 'published' | 'archived'
  created_at: string
  updated_at: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
}

export type TaskType = 'transcription' | 'edition' | 'summary' | 'source_extraction'
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed'
```

- Mirror backend response schemas exactly — keep field names in `snake_case` as returned by the API (don't transform to camelCase).
- Use `string` for UUIDs and ISO date strings — don't create wrapper types.
- Use union types / string literals for enums (`'draft' | 'published'`), not TypeScript `enum`.

## Tailwind CSS

### General Rules

- **Tailwind utility classes are the primary styling method** — avoid custom CSS.
- Use `<style scoped>` only for things Tailwind cannot express (complex animations, pseudo-element content).
- Never use `@apply` to create abstract utility classes — it defeats the purpose of Tailwind.
- Use Tailwind's responsive prefixes consistently: `sm:`, `md:`, `lg:`.
- Use Tailwind's color palette — don't hardcode hex values. Extend the theme in `tailwind.config.js` if the project needs custom colors.

### Common Patterns

```html
<!-- Card pattern -->
<div class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">

<!-- Page heading -->
<h1 class="text-2xl font-bold text-gray-900">

<!-- Subtle text / metadata -->
<span class="text-sm text-gray-500">

<!-- Truncated text -->
<p class="truncate">

<!-- Responsive grid -->
<div class="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
```

### Dark Mode

- Do not implement dark mode unless explicitly requested.

## Headless UI

Use Headless UI (Vue) for all interactive UI patterns that require accessibility: dialogs/modals, dropdowns/menus, listboxes/selects, comboboxes, disclosure/accordion, tabs, popovers, and toggles/switches.

### Import Pattern

```typescript
import {
  Dialog,
  DialogPanel,
  DialogTitle,
  Menu,
  MenuButton,
  MenuItem,
  MenuItems,
  Listbox,
  ListboxButton,
  ListboxOption,
  ListboxOptions,
  Switch,
  TransitionRoot,
  TransitionChild,
} from '@headlessui/vue'
```

### Usage Rules

- **Always wrap dialogs in `TransitionRoot` / `TransitionChild`** for smooth open/close animations.
- **Always provide accessible labels** — `DialogTitle` for modals, `aria-label` for icon-only buttons.
- **Style state via slot props** — Headless UI exposes `active`, `selected`, `open`, `checked` etc. as slot props. Use them with Tailwind classes:

```vue
<MenuItem v-slot="{ active }">
  <button :class="[active ? 'bg-gray-100 text-gray-900' : 'text-gray-700', 'block w-full px-4 py-2 text-left text-sm']">
    Edit
  </button>
</MenuItem>
```

- **Don't build custom modals, dropdowns, or select menus from scratch** — always use Headless UI. It handles focus trapping, keyboard navigation, and screen readers.
- **Keep Headless UI components in `components/ui/`** — wrap them in project-specific components if reused with consistent styling:

```
components/ui/
├── AppDialog.vue          # Wraps Dialog + transitions + standard styling
├── AppDropdown.vue        # Wraps Menu with standard trigger button
├── AppSelect.vue          # Wraps Listbox with label + error state
├── AppSwitch.vue          # Wraps Switch with label
└── ConfirmDialog.vue      # Confirmation modal (delete, publish, etc.)
```

## Authentication (Clerk)

### Setup

```typescript
// main.ts
import { clerkPlugin } from '@clerk/vue'

app.use(clerkPlugin, {
  publishableKey: import.meta.env.VITE_CLERK_PUBLISHABLE_KEY,
})
```

### Auth Composable

```typescript
// composables/useAuth.ts
import { useUser, useAuth as useClerkAuth } from '@clerk/vue'
import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
})

export function useAuth() {
  const { user, isLoaded, isSignedIn } = useUser()
  const { getToken } = useClerkAuth()

  const role = computed(() => user.value?.publicMetadata?.role as string ?? 'reader')

  // Set up auth interceptor once
  apiClient.interceptors.request.use(async (config) => {
    const token = await getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  return { user, isLoaded, isSignedIn, role, apiClient }
}
```

- **All API calls go through the shared `apiClient`** with the auth interceptor — components never create their own axios instances.
- **Never store the token in localStorage** — always get a fresh token via `getToken()`.
- Configure a response interceptor for global error handling (401 → redirect to sign-in, 5xx → toast).

### Permissions

Permissions are defined in `.cursor/rules/access.md` — that file is the single source of truth. The frontend `usePermissions` composable implements the matrix from that document.

```typescript
// composables/usePermissions.ts
// See access.md for the full PERMISSIONS map and implementation
import { useAuth } from './useAuth'

export function usePermissions() {
  const { role } = useAuth()
  const can = (resource: string, action: string): boolean => { /* ... */ }
  return { can, role }
}
```

Use `can()` in templates:

```vue
<button v-if="can('lessons', 'delete')" @click="deleteLesson">Delete</button>
```

Use `can()` in route guards:

```typescript
// router/index.ts
router.beforeEach((to, from, next) => {
  const { can } = usePermissions()
  const { resource, action } = to.meta
  if (resource && action && !can(resource, action)) {
    next({ name: 'not-authorized' })
  } else {
    next()
  }
})
```

## API Client Layer

### Structure

```typescript
// api/client.ts
import axios from 'axios'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Auth interceptor is set up in useAuth composable

// Global error response interceptor
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Redirect to Clerk sign-in
    }
    return Promise.reject(error)
  },
)
```

```typescript
// api/lessons.ts
import { apiClient } from './client'
import type { Lesson, PaginatedResponse } from './types'

export const lessonsApi = {
  list: (params?: { page?: number; status?: string }) =>
    apiClient.get<PaginatedResponse<Lesson>>('/api/v1/lessons', { params }).then(r => r.data),

  get: (id: string) =>
    apiClient.get<Lesson>(`/api/v1/lessons/${id}`).then(r => r.data),

  create: (data: Partial<Lesson>) =>
    apiClient.post<Lesson>('/api/v1/lessons', data).then(r => r.data),

  update: (id: string, data: Partial<Lesson>) =>
    apiClient.patch<Lesson>(`/api/v1/lessons/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    apiClient.delete(`/api/v1/lessons/${id}`),
}
```

### Rules

- **One API module per resource** — `lessons.ts`, `tasks.ts`, `courses.ts`, etc.
- **All API calls go through the `apiClient` axios instance** — components never call `axios.get()` or `fetch()` directly.
- **Type every response** — use the interfaces from `api/types.ts` with axios generics (`apiClient.get<Lesson>(...)`).
- **Unwrap responses** — API functions return `r.data` (the payload), not the full axios response.
- **Handle errors centrally** — the response interceptor handles 401/5xx. Resource-specific errors (404, 422) are caught in composables or views and displayed via toast.
- **No data transformation in the API layer** — return the backend response as-is. Transform in composables or computed properties if needed.

## Task Polling

Tasks (transcription, edition, summary, source extraction) are long-running. The frontend polls for status updates.

```typescript
// composables/useTask.ts
export function useTask(taskId: Ref<string | null>) {
  const task = ref<Task | null>(null)
  const isPolling = ref(false)
  let intervalId: number | null = null

  async function poll() {
    if (!taskId.value) return
    isPolling.value = true
    task.value = await tasksApi.get(taskId.value)
    if (task.value.status === 'completed' || task.value.status === 'failed') {
      stop()
    }
  }

  function start(intervalMs = 3000) {
    poll()
    intervalId = window.setInterval(poll, intervalMs)
  }

  function stop() {
    if (intervalId) clearInterval(intervalId)
    isPolling.value = false
  }

  onUnmounted(stop)

  return { task, isPolling, start, stop }
}
```

- Poll every 3 seconds for running tasks.
- **Always stop polling on `onUnmounted`** — prevent memory leaks.
- Show a progress indicator (spinner or status badge) while a task is `pending` or `running`.
- On `completed`, refresh the related data (e.g. reload the lesson to show the new transcript).
- On `failed`, display the error message from `task.error`.

## File Uploads (Audio to R2)

Use presigned URLs from the backend — never upload directly from the frontend to R2 without a presigned URL.

```typescript
// 1. Request presigned URL from backend
const { upload_url, file_key } = await lessonsApi.getUploadUrl(lessonId)
// 2. Upload directly to R2 (use raw axios, not apiClient — different host, no auth needed)
await axios.put(upload_url, file, {
  headers: { 'Content-Type': 'audio/mpeg' },
  onUploadProgress: (e) => { progress.value = Math.round((e.loaded * 100) / (e.total ?? 1)) },
})
// 3. Confirm upload to backend
await lessonsApi.confirmUpload(lessonId, file_key)
```
- Validate file type (`audio/mpeg`, `audio/mp4`, `audio/wav`) and size on the frontend before uploading.
- Display file size and duration when possible.

## Sefaria Sources

Sources extracted from lessons link to Sefaria. Format references as clickable links:

```typescript
// utils/sefaria.ts
export function sefariaUrl(ref: string): string {
  return `https://www.sefaria.org/${encodeURIComponent(ref.replace(/ /g, '_'))}`
}
```

- Display source references with both Hebrew and English names when available.
- Open Sefaria links in a new tab (`target="_blank" rel="noopener"`).

## Internationalization (Vue I18n)

The app supports **French** (default) and **English**. All user-facing text must be translated — no hardcoded strings in templates.

### Setup

```typescript
// i18n/index.ts
import { createI18n } from 'vue-i18n'
import fr from './locales/fr.json'
import en from './locales/en.json'

export const i18n = createI18n({
  legacy: false,          // Use Composition API mode
  locale: 'fr',           // Default locale
  fallbackLocale: 'en',
  messages: { fr, en },
})
```

```typescript
// main.ts
import { i18n } from './i18n'
app.use(i18n)
```

### File Structure

```
src/i18n/
├── index.ts              # i18n instance creation
└── locales/
    ├── fr.json           # French translations (primary)
    └── en.json           # English translations (fallback)
```

### Locale File Organization

Use nested keys grouped by feature/view, not flat keys:

```json
{
  "common": {
    "save": "Enregistrer",
    "cancel": "Annuler",
    "delete": "Supprimer",
    "confirm": "Confirmer",
    "loading": "Chargement...",
    "error": "Une erreur est survenue",
    "noResults": "Aucun résultat"
  },
  "lessons": {
    "title": "Cours",
    "create": "Nouveau cours",
    "status": {
      "draft": "Brouillon",
      "published": "Publié",
      "archived": "Archivé"
    },
    "fields": {
      "rabbi": "Rabbin",
      "title": "Titre",
      "date": "Date"
    }
  },
  "tasks": {
    "transcription": "Transcription",
    "edition": "Édition",
    "summary": "Résumé",
    "sourceExtraction": "Extraction des sources",
    "status": {
      "pending": "En attente",
      "running": "En cours",
      "completed": "Terminé",
      "failed": "Échoué"
    }
  }
}
```

### Usage Rules

**In templates** — use `$t()`:

```vue
<template>
  <h1>{{ $t('lessons.title') }}</h1>
  <button>{{ $t('common.save') }}</button>
  <!-- With interpolation -->
  <p>{{ $t('lessons.deleteConfirm', { title: lesson.title }) }}</p>
</template>
```

**In `<script setup>`** — use the `useI18n` composable:

```typescript
import { useI18n } from 'vue-i18n'

const { t, locale } = useI18n()

const statusLabel = computed(() => t(`tasks.status.${task.value.status}`))
```

**Critical rules:**

- **Never hardcode user-facing strings** — every label, button text, placeholder, error message, toast, and confirmation dialog must use `t()` / `$t()`.
- **Both locale files must stay in sync** — when adding a key to `fr.json`, always add the corresponding key to `en.json` in the same commit.
- **Keys are English, values are translated** — key path `lessons.create` has value `"Nouveau cours"` in `fr.json` and `"New lesson"` in `en.json`.
- **Use nested keys, not dots in key names** — `lessons.status.draft`, not `"lessons.status.draft"` as a flat key.
- **Interpolation for dynamic content** — use named parameters: `"deleteConfirm": "Supprimer {title} ?"`, not string concatenation.
- **Pluralization** — use Vue I18n's plural syntax: `"lessonCount": "Aucun cours | {count} cours | {count} cours"`.
- **Do not translate Sefaria references, rabbi names, or Hebrew Torah terms** — these are proper nouns and should be passed as interpolation values, not translation keys.
- **Dates and numbers** — use Vue I18n's `$d()` and `$n()` formatters, or `Intl.DateTimeFormat` / `Intl.NumberFormat` with the current locale. Do not format dates manually.

### Locale Switching

```vue
<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { locale } = useI18n()
const toggleLocale = () => {
  locale.value = locale.value === 'fr' ? 'en' : 'fr'
  localStorage.setItem('locale', locale.value)
}
</script>
```

- Persist the user's locale preference in `localStorage`.
- Load the saved locale on app init in `main.ts`.
- The locale switcher should be in the app header/navigation.

## Router

### Route Definition Pattern

```typescript
// router/index.ts
const routes = [
  {
    path: '/lessons',
    name: 'lessons-list',
    component: () => import('@/views/LessonsListView.vue'),
    meta: { resource: 'lessons', action: 'read' },
  },
  {
    path: '/lessons/:id',
    name: 'lesson-detail',
    component: () => import('@/views/LessonDetailView.vue'),
    meta: { resource: 'lessons', action: 'read' },
  },
  {
    path: '/tasks',
    name: 'tasks',
    component: () => import('@/views/TasksView.vue'),
    meta: { resource: 'tasks', action: 'read' },
  },
  // ...
]
```

- **Always lazy-load views** with dynamic `import()`.
- **Always set `meta.resource` and `meta.action`** for permission-gated routes.
- The global navigation guard checks `meta` against `usePermissions().can()`.

## Error Handling

- API errors → caught in composables or views → displayed via toast notifications.
- 401 responses → redirect to Clerk sign-in.
- 403 responses → display "insufficient permissions" message, redirect to safe page.
- Network errors → display retry-able error state.
- **Never show raw error objects or stack traces to users.**

## Do NOT

- Do not use Options API or `defineComponent()`.
- Do not use `this` — it doesn't exist in `<script setup>`.
- Do not use Vuex — use Pinia if global state is needed, or composables for shared logic.
- Do not create additional axios instances — use the shared `apiClient` from `api/client.ts`.
- Do not call `axios.get/post/...` directly in components — always go through the API layer (`api/*.ts`).
- Do not build custom modals, dropdowns, selects, or tabs from scratch — use Headless UI.
- Do not use `@apply` extensively in CSS — use Tailwind classes directly in templates.
- Do not store auth tokens in localStorage or sessionStorage.
- Do not hardcode API base URLs — use `import.meta.env.VITE_API_BASE_URL`.
- Do not use `any` in TypeScript — type everything. Use `unknown` if the type is genuinely unknown.
- Do not create god-components with 300+ lines — split into smaller composable pieces.
- Do not duplicate the permission matrix — always reference `usePermissions()` which implements `access.md`.

## Environment Variables

```bash
VITE_API_BASE_URL=https://api.example.com
VITE_CLERK_PUBLISHABLE_KEY=pk_live_...
```

- All frontend env vars must be prefixed with `VITE_`.
- Never put secrets in frontend env vars — they are embedded in the build.

## Deployment

- Build with `vite build` — output to `dist/`.
- Deploy as a static site on Render.com or Cloudflare Pages.
- Configure SPA fallback: all routes → `index.html` (for Vue Router history mode).
- Set `VITE_API_BASE_URL` as a build-time environment variable.
