# User Access Management — Round 2 Design

Date: 2026-10-13 · Module: `user_access_management` (Odoo 20) · Builds on: `2026-10-13-uam-admin-features-design.md`
Status: approved in chat (frontend approved; Part B picks: gaps 2, 4, 5 + useful 1, 2, 3, 4 without Grant; new: temp-access warning)

## Goal

Make every screen match the dashboard's visual identity and add seven behaviour changes that close gaps and make the module more useful day to day.

## Out of scope

- Granting/removing rights from Simulation (user will decide later).
- Blocked-attempt log, child-line lock gap, unusual-activity alerts (not picked).

## Visual identity (shared by all screens)

Signal palette, already used by the dashboard (`static/src/dashboard/dashboard.scss`):
teal `#0E9F8E` = active/online/original · amber `#D99A1E` = warning/away/copy/expiring · crimson `#B42339` = needs action/stale/locked · indigo `#3554D1` = links/accent. Surfaces use Odoo/Bootstrap theme variables (dark mode safe).

Move the palette to `static/src/scss/uam_tokens.scss` (CSS custom properties on `.o_web_client` scoped classes `o_uam_*`) so views and the dashboard share it.

Rules:
- Native Odoo view features only (kanban, badges, decorations, ribbons, stat buttons, statusbar, progressbar, graph/pivot, action `help`). No custom JS for views.
- Icons: Odoo 20 `oi` font (`<span class="oi" data-icon="…"/>`, button `icon="oi-…"` where supported). Remove every `fa` usage (they render blank in Odoo 20).
- Every list/kanban action gets a plain-language empty-state `help`.
- OWL templates use `t-out`, never `t-esc`.

## Screens (Part A)

| Screen | Change |
|---|---|
| Users | Kanban default: avatar with status ring, current page, stat chips (groups, rights, locks, temp access, prints). Form: stat buttons for the same + a Timeline page (see U1). |
| Access Lock | Kanban grouped by user/group; state badge: active (crimson), forever (dark), expired (muted). Form: state ribbon, "Unlock now" (archive) and "Extend 1 day / 1 week" buttons. Lock target shows user OR group (see U2). |
| Temporary Access | Kanban grouped by state; "time left" bar (amber < 24 h). |
| Print Log | List: avatar, Original solid teal / Copy dashed amber badges, "By document" grouping with copy count. |
| Model Usage | Add graph + pivot (views per model per day); views badge coloured by volume. |
| Change Log, Work Updates, Groups, Access Rights | Avatars, add/remove badges (teal/crimson), default grouping where useful. |
| Simulation | Coloured ✓ / ✓* / ✗ cells (teal / amber / crimson) + compare mode (U4). |

## Behaviour changes (Part B)

### G2 — No self-lockout
`uam.access.lock` refuses (ValidationError on create/write):
- any lock on models `uam.access.lock` or `uam.lock.method`;
- a lock whose target (the user, or any member of the target group) is in `base.group_system` when the model is `res.users`, `res.groups` or `ir.access`.

### G4 — Print Log retention
Setting `uam_print_retention_days` (Integer, default 180, `0` = keep forever, config param `user_access_management.print_retention_days`). Daily `@api.autovacuum` deletes `uam.print.log` rows older than the limit together with their attachments.

### G5 — "PDFs today" in the admin's timezone
Dashboard tile domain uses the start of today in the user's tz converted to UTC (same day boundary as `context_today`).

### U1 — One page per user
User form:
- Stat buttons: Groups, Access Rights (existing) + Locks (direct and via the user's groups), Temporary Access, Prints, Model Usage, Changes.
- New "Timeline" notebook page: computed Html, newest first, last 50 events merged from change log, locks (created/expired), temporary access (granted/expired/cancelled) and prints. Each line: time (user tz), coloured icon, plain sentence. Escaped via Markup formatting.

### U2 — Lock by group
`uam.access.lock` gets `group_id` (Many2one `res.groups`). Exactly one of `user_id` / `group_id` is required (constraint). Membership is live: `_check` matches `user_id = uid` OR `group_id in uid.all_group_ids`. Display name: "<user or group> – <model>". Lists/kanban/dashboard count both kinds.

### U3 — Act on stale logins
Two actions on the Users list/kanban (multi-select, `confirm` prompt):
- **Archive stale users** — archives selected users that are stale; non-stale selections are skipped and reported in a notification ("Archived 3, skipped 1 that logged in recently").
- **Send login reminder** — emails selected stale users with an active email, using a mail template "Your account hasn't been used in N days"; same skip/report behaviour. Never archives the current user or any `base.group_system` user.

### U4 — Compare two users (Simulation)
`uam.access.simulation` gets optional `user2_id`. When set, each model row shows both users' cells side by side; rows where any operation differs are highlighted (amber left border) and a "Only differences" toggle (`only_diff` Boolean) hides identical rows. Read-only.

### N1 — Temporary access warning for the user
New JS service (internal users only), on web client start and every 15 minutes:
- calls `user.temp.access.uam_my_expiring()` (`@api.model`, sudo, current user only) → active temporary accesses of `env.uid`: group names, `date_to` formatted in the user's tz, `hours_left`.
- shows a sticky notification per access, once per session: "Your extra access (Sales / Administrator) ends today at 17:00" — `warning` type if `hours_left < 24`, else `info`.
- shows it again once when `hours_left < 1`.

## Security
- `uam_my_expiring` returns only the caller's own rows.
- Stale actions and all new fields/actions are `base.group_system` only.
- New mail template and settings fields are admin-only.

## Testing
One test per behaviour (G2, G4, G5, U1 timeline contents, U2 group match incl. live membership change, U3 skip rules incl. self/admin protection, U4 diff rows, N1 own-rows-only + hours_left). Full suite via `scripts/test_module.sh`. Browser screenshot pass of every screen on :8070.

## Build order
1. Shared tokens + icon migration + empty states (foundation)
2. U2 lock by group + G2 self-lockout (same model)
3. G4 retention + G5 tz tile
4. U1 user page (stat buttons + timeline)
5. U3 stale actions
6. U4 compare users
7. N1 temp-access warning
8. Part A screen restyles (Users kanban/form, Lock, Temp Access, Print Log, Usage, Logs, Groups, Rights, Simulation cells)
