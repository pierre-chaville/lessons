# Access Control Rules

This document defines the role-based access control (RBAC) model for the entire application. It is the single source of truth — both frontend and backend must enforce these rules consistently.

## Roles (ordered by privilege)

1. **reader** — default role for invited users
2. **editor** — can modify lesson content
3. **publisher** — manages content lifecycle (create, publish, delete)
4. **admin** — unrestricted access

Roles are managed in Clerk and transmitted via JWT claims. A user has exactly one role.

## Resources and Permissions

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
| **Tasks**      | read   | ❌     | ❌     | ✅        | ✅    |
|                | create | ❌     | ❌     | ✅        | ✅    |
|                | cancel | ❌     | ❌     | ❌        | ✅    |
| **Configuration** | read | ❌   | ❌     | ✅        | ✅    |
|                | update | ❌     | ❌     | ❌        | ✅    |
| **Users**      | read   | ❌     | ❌     | ❌        | ✅    |
|                | manage | ❌     | ❌     | ❌        | ✅    |

## Backend Enforcement

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

If a user lacks permission, return `403 Forbidden` with `{"detail": "Insufficient permissions"}`.

## Frontend Enforcement

Frontend permission checks are for **UX only** (hiding buttons, disabling actions, redirecting). They do not replace backend checks. The backend is always the authority.

### Permission helper

```javascript
// composables/usePermissions.js
const PERMISSIONS = {
  lessons:       { read: ['reader','editor','publisher','admin'], create: ['publisher','admin'], update: ['editor','publisher','admin'], delete: ['publisher','admin'] },
  courses:       { read: ['reader','editor','publisher','admin'], create: ['publisher','admin'], update: ['publisher','admin'], delete: ['publisher','admin'] },
  themes:        { read: ['reader','editor','publisher','admin'], create: ['publisher','admin'], update: ['publisher','admin'], delete: ['publisher','admin'] },
  sources:       { read: ['reader','editor','publisher','admin'], create: ['publisher','admin'], update: ['publisher','admin'], delete: ['publisher','admin'] },
  tasks:         { read: ['publisher','admin'], create: ['publisher','admin'], cancel: ['admin'] },
  configuration: { read: ['publisher','admin'], update: ['admin'] },
  users:         { read: ['admin'], manage: ['admin'] },
}

export function usePermissions(userRole) {
  const can = (resource, action) => PERMISSIONS[resource]?.[action]?.includes(userRole) ?? false
  return { can }
}
```

### UI behavior

- **Hide** elements the user cannot interact with (don't show a disabled "Delete" button to a reader — hide it entirely).
- **Redirect** unauthorized users to the appropriate fallback view if they navigate to a restricted page.
- **Never** display tasks or configuration UI to readers or editors.

## Rules for AI Assistants (Cursor / Claude Code)

- When creating a new endpoint, always include the appropriate `require_role()` dependency based on this table.
- When creating a new frontend view or component with actions, check this table and conditionally render based on `can(resource, action)`.
- When adding a new resource, update this document first with its permission matrix before writing code.
- Never hardcode role names as raw strings scattered across the codebase — reference the centralized permission definitions.
- If a permission is ambiguous or not listed here, ask — do not guess.
