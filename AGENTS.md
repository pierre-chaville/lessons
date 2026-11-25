# AGENTS.md — Torah Lessons Transcription Platform

Invitation-only platform that transcribes Torah lessons (MP3), produces edited long-form versions, extracts Sefaria sources and generates summaries.
- **Backend**: FastAPI + SQLModel + PostgreSQL, Clerk auth, Cloudflare R2, LLM calls via LangChain, DB-backed task queue.
- **Frontend**: Vue 3 (`<script setup lang="ts">`) + Vite + Tailwind + Headless UI + Vue I18n (fr/en), Clerk.

## Detailed rules by area — read before editing

These files contain the detailed conventions. They are mandatory:

- **Before creating or modifying any file under `backend/`** → read `.claude/rules/backend.md` (applies to everything under `backend/`).
- **Before creating or modifying any file under `frontend/`** → read `.claude/rules/frontend.md` (applies to everything under `frontend/`).

(Claude Code loads these automatically based on the files touched; other agents must open them explicitly.)

The access-control rules below apply to **all** code, frontend and backend, and are the single source of truth.

---

## Access Control

This section defines the role-based access control (RBAC) model for the entire application. It is the single source of truth — both frontend and backend must enforce these rules consistently.

### Roles (ordered by privilege)

1. **reader** — default role for invited users
2. **editor** — can modify lesson content
3. **publisher** — manages content lifecycle (create, publish, delete)
4. **admin** — unrestricted access

Roles are managed in Clerk and transmitted via JWT claims. A user has exactly one role.

### Resources and Permissions

| Resource       | Action | reader | editor | publisher | admin |
|---------------|--------|--------|--------|-----------|-------|
| **Lessons**    | read   | ✅     | ✅     | ✅        | ✅    |
|                | create | ❌     | ❌     | ✅        | ✅    |
|                | update | ❌     | ✅     | ✅        | ✅    |
|                | delete | ❌     | ❌     | ✅        | ✅    |
| **Courses**    | read   | ✅     | ✅     | ✅        | ✅    |
|                | create | ❌     | ❌     | ✅        | ✅    |
|                | update | ❌     | ❌     | ✅        | ✅    |
|                | delete | ❌     | ❌     | ✅        | ✅    |
| **Themes**     | read   | ✅     | ✅     | ✅        | ✅    |
|                | create | ❌     | ❌     | ✅        | ✅    |
|                | update | ❌     | ❌     | ✅        | ✅    |
|                | delete | ❌     | ❌     | ✅        | ✅    |
| **Sources**    | read   | ✅     | ✅     | ✅        | ✅    |
|                | create | ❌     | ❌     | ✅        | ✅    |
|                | update | ❌     | ❌     | ✅        | ✅    |
|                | delete | ❌     | ❌     | ✅        | ✅    |
| **Glossary**   | read   | ❌     | ✅     | ✅        | ✅    |
|                | create | ❌     | ❌     | ✅        | ✅    |
|                | update | ❌     | ❌     | ✅        | ✅    |
|                | delete | ❌     | ❌     | ✅        | ✅    |
| **Tasks**      | read   | ❌     | ✅*    | ✅        | ✅    |
|                | create | ❌     | ✅*    | ✅        | ✅    |
|                | cancel | ❌     | ❌     | ❌        | ✅    |
| **Model presets** | read | ❌   | ❌     | ✅        | ✅    |
|                | create | ❌     | ❌     | ❌        | ✅    |
|                | update | ❌     | ❌     | ❌        | ✅    |
|                | delete | ❌     | ❌     | ❌        | ✅    |
| **Configuration** | read | ❌   | ❌     | ✅        | ✅    |
|                | update | ❌     | ❌     | ❌        | ✅    |
| **Users**      | read   | ❌     | ❌     | ✅        | ✅    |
|                | manage | ❌     | ❌     | ✅†       | ✅    |
| **My preferences** | read | ✅  | ✅     | ✅        | ✅    |
|                | update | ✅     | ✅     | ✅        | ✅    |

\* **Editors can read and create tasks only on lessons they are assigned to as editor.** This is a resource-level check that comes *in addition to* the role check: the role alone is not enough.

† **Publishers manage users with restrictions**: they cannot grant the `admin` role (create, invite or role change), and cannot change the role of or delete a user who is `admin`. "Manage" covers creating, inviting, revoking invitations, changing roles and deleting users.

**My preferences**: personal display settings of the signed-in user (e.g. how Hebrew is displayed in lessons). A user only ever reads and updates **their own** preferences, identified by the token's user id — no endpoint takes a user id, so nobody (admin included) reads or changes another user's preferences.

**Glossary**: covers the Hebrew-keyed glossary and the read-only legacy glossary. YAML export (glossary and legacy) is a *read*; YAML import is a *create/update*. Exception: reading a **lesson** includes the display data (Hebrew, transliteration, translation, type, Sefaria title/ref) of the glossary entries that appear in that lesson's edited text and summary (`GET /lessons/{id}/hebrew-terms`), so every role that can read the lesson can display it in their chosen Hebrew mode. This does not grant access to the glossary itself.

### Backend Enforcement

Every endpoint must check permissions. Use the `require_role()` dependency:

```python
# Simple role check — user must have one of the listed roles
@router.post("/lessons", status_code=201)
async def create_lesson(
    user: ClerkUser = Depends(require_role("publisher", "admin")),
    ...
):
```

For actions where the permission depends on the action type (e.g. editor can update but not create lessons), use explicit per-endpoint role lists — do not implement hierarchical role inheritance in code, keep it flat and readable.

**Resource-level checks.** When a permission depends on the user's relationship to a specific resource (e.g. an editor reading or creating a task on a lesson), the role check is not sufficient. Load the resource, then verify the relationship in a dedicated helper (e.g. `ensure_lesson_editor(user, lesson, session)` in `dependencies/auth.py`) before doing anything. `publisher` and `admin` bypass the assignment check.
For list endpoints (e.g. `GET /tasks`), editors get results **filtered in the query** to their assigned lessons — never fetch everything and filter in Python.

If a user lacks permission, return `403 Forbidden` with `{"detail": "Insufficient permissions"}`.

### Frontend Enforcement

Frontend permission checks are for **UX only** (hiding buttons, disabling actions, redirecting). They do not replace backend checks. The backend is always the authority.

#### Permission helper

```javascript
// composables/usePermissions.js
const PERMISSIONS = {
  lessons:       { read: ['reader','editor','publisher','admin'], create: ['publisher','admin'], update: ['editor','publisher','admin'], delete: ['publisher','admin'] },
  courses:       { read: ['reader','editor','publisher','admin'], create: ['publisher','admin'], update: ['publisher','admin'], delete: ['publisher','admin'] },
  themes:        { read: ['reader','editor','publisher','admin'], create: ['publisher','admin'], update: ['publisher','admin'], delete: ['publisher','admin'] },
  sources:       { read: ['reader','editor','publisher','admin'], create: ['publisher','admin'], update: ['publisher','admin'], delete: ['publisher','admin'] },
  glossary:      { read: ['editor','publisher','admin'], create: ['publisher','admin'], update: ['publisher','admin'], delete: ['publisher','admin'] },
  tasks:         { read: ['editor','publisher','admin'], create: ['editor','publisher','admin'], cancel: ['admin'] }, // editor: only on assigned lessons, see below
  model_presets: { read: ['publisher','admin'], create: ['admin'], update: ['admin'], delete: ['admin'] },
  configuration: { read: ['publisher','admin'], update: ['admin'] },
  users:         { read: ['publisher','admin'], manage: ['publisher','admin'] }, // publisher: cannot grant or touch admin, see below
  preferences:   { read: ['reader','editor','publisher','admin'], update: ['reader','editor','publisher','admin'] }, // own preferences only
}

export function usePermissions(userRole) {
  const can = (resource, action) => PERMISSIONS[resource]?.[action]?.includes(userRole) ?? false
  return { can }
}
```

#### UI behavior

- **Hide** elements the user cannot interact with (don't show a disabled "Delete" button to a reader — hide it entirely).
- **Redirect** unauthorized users to the appropriate fallback view if they navigate to a restricted page.
- **Never** display tasks UI to readers. **Never** display configuration UI to readers or editors.
- Editors can open the tasks view; it shows only tasks on their assigned lessons (the backend filters the list).
- Task launch actions and task status on a lesson (transcribe, edit, summarize, extract sources) are shown to editors **only if they are assigned to that lesson as editor**. `can('tasks', ...)` checks the role only; combine it with the lesson-assignment check in the component.

### Rules for AI Assistants (Claude Code / Codex)

- When creating a new endpoint, always include the appropriate `require_role()` dependency based on this table.
- When creating a new frontend view or component with actions, check this table and conditionally render based on `can(resource, action)`.
- When adding a new resource, update this section first with its permission matrix before writing code.
- Never hardcode role names as raw strings scattered across the codebase — reference the centralized permission definitions.
- If a permission is ambiguous or not listed here, ask — do not guess.
