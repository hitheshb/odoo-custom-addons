# User Access Management — Admin Features Design

Date: 2026-10-13 · Module: `user_access_management` (Odoo 20) · Status: approved in chat, awaiting spec review

## Goal

Give the administrator one home-page dashboard plus four tools: Print Log, Access Lock,
read-only Access Simulation, and a configurable stale-login threshold. All features live in
the existing `user_access_management` module and are visible to `base.group_system` only.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Copy counting | Per document, global across all users. First download ever = Original, then Copy-1, Copy-2… |
| Re-download | Serve the exact PDF bytes saved at download time (stored as `ir.attachment`). No watermark. |
| Lock method picker | Auto-filled tick list: form-view `type="object"` buttons + Create, Edit, Delete, Print. |
| "Used a model" | Opening a page counts (client-side route tracking). |
| Simulation | Read-only for now. Grant/remove is a later phase. |
| Lock enforcement | Checked at web entry points (`call_kw`, `call_button`, `/report/download`, JSON-2). |
| Dashboard | OWL client action, auto-refresh every 30 s, home page for system admins. |

## Data model

### `uam.print.log` (new)
- `user_id` (res.users), `report_id` (ir.actions.report), `model` (Char), `res_ids` (Char, sorted comma-joined ids),
  `record_name` (Char), `copy_no` (Integer, 0 = Original), `label` (computed: "Original" / "Copy-N"),
  `attachment_id` (ir.attachment), `create_date`.
- Unique constraint on (`report_id`, `res_ids`, `copy_no`).
- Read-only in UI; no create/write/unlink from views.

### `uam.access.lock` (new)
- `user_id`, `model_id` (ir.model), `method_ids` (M2m `uam.lock.method`, domain on `model_id`),
  `date_until` (Datetime), `forever` (Boolean), `active` (Boolean), `note`.
- Constraint: `forever` or `date_until` required; `date_until` must be in the future at create.
- Hourly cron archives locks with `date_until <= now` and not `forever`.

### `uam.lock.method` (new)
- `model_id`, `name` (technical: `create`, `write`, `unlink`, `print`, or a button method name), `label`.
- `_sync_for_model(model)` builds rows from the model's default form view arch (`button[@type='object']`)
  plus the four fixed entries. Called by an onchange on `uam.access.lock.model_id`. Existing rows are reused.

### `uam.model.usage` (new)
- `user_id`, `model` (Char), `date` (Date), `view_count` (Integer), `first_seen`, `last_seen` (Datetime).
- Unique (`user_id`, `model`, `date`). Upsert via SQL `ON CONFLICT DO UPDATE`.

### `uam.access.simulation` (new, TransientModel)
- `user_id`, `model_id` (optional), `module_id` (ir.module.module, optional), `report_html` (computed Html table):
  model × read/create/write/unlink → ✓/✗ + granting group names.
- Uses `self.env(user=user)[model].has_access(op)`. "Via group" = user's groups whose active `ir.access`
  rows for that model include the operation (respecting the Odoo 20 `operation` column).

### `res.users` (extend)
- `uam_current_page` (Char), `uam_last_seen` (Datetime).
- `uam_login_stale` gains `search='_search_uam_login_stale'`; both compute and search use `_uam_stale_limit()`.
- `uam_track(model, page)` (`@api.model`): writes current page/last seen, upserts today's `uam.model.usage`.
- Online/away uses the existing `im_status` field.

### `res.config.settings` (extend)
- `uam_stale_login_days` (Integer, default 3) → `ir.config_parameter` `user_access_management.stale_login_days`.

## Flows

### Access Lock check — `controllers/main.py`
1. Extend `DataSet.call_kw` and `DataSet.call_button`; before delegating, call
   `env['uam.access.lock']._check(model, method, args)`.
2. Method mapping: `web_save` without id / `create` / `web_save_multi` → `create`;
   `web_save` with id / `write` → `write`; `unlink` → `unlink`; anything else → the method name itself.
3. Match = active lock for (uid, model, method) where `forever` or `date_until > now` → `UserError`
   "Locked by administrator until <date>: <label> on <model name>".
4. `ReportController.report_download` runs the same check with method `print`.
5. JSON-2 controller (`/json/2/<model>/<method>`) gets the same check.
6. Server-internal calls (crons, automated actions) are not blocked by design.

### Print capture — same controller file
1. Extend `report_download`; after `super()` returns, act only for `qweb-pdf` with docids.
2. `copy_no = search_count(same report_id, same sorted res_ids)`.
3. Store response bytes as `ir.attachment` (res_model `uam.print.log`), create the log row.
4. On unique-constraint collision, retry once with a fresh count.
5. Log row has a Download button → `/web/content/<attachment_id>?download=true`.

### Page tracking — `static/src/page_tracker.js`
1. Service listens to `routerBus` `ROUTE_CHANGE` (Odoo 20 `@web/core/browser/router`).
2. Reads current action's `res_model` and breadcrumb names; throttled to one call per 10 s.
3. Calls `res.users.uam_track(model, page)`.

### Stale days
- `_uam_stale_limit()` = now − `stale_login_days` days. Filter in `user_views.xml` becomes
  `[('uam_login_stale', '=', True)]` with label "Stale Login".

## Dashboard

- Client action tag `uam_dashboard`; data from one `uam.dashboard.get_data(date)` RPC (AbstractModel).
- Tiles: Online, Away, Stale logins, Active locks, Temp access expiring <24 h, PDFs today. Each opens a filtered list.
- "Users right now": status dot, name, `uam_current_page`, last seen / last login, stale badge.
- "Models used on <date>": date picker → `uam.model.usage` rows for that date. Click user → their usage list.
- "Recent prints": last 10 `uam.print.log` rows with label and ⬇ download.
- Auto-refresh every 30 s.
- Home page: `post_init_hook` sets `action_id` to the dashboard action for all `base.group_system` users;
  root menu "User Access" opens the dashboard.

## Menus

- User Access › Dashboard (seq 1)
- Privileges › Access Lock, Access Simulation
- Logs › Print Log
- Configuration › Settings

## Security

- All new models: `ir.access.csv` rows for `base.group_system` only (Odoo 20 `operation` column).
- `uam.print.log`: `operation` = read for admins; rows created via `sudo()` in the controller.
- `uam.model.usage`: written only via `sudo()` inside `uam_track`.

## Testing

`tests/test_uam_features.py`:
- Locked user calling `action_confirm` on `sale.order` → blocked; after `date_until` passes → allowed.
  (Use a module-agnostic model if `sale` is not a dependency, e.g. `res.partner` create/write.)
- Two downloads of the same document → `copy_no` 0 then 1.
- Changing `stale_login_days` changes `search([('uam_login_stale','=',True)])` results.
- Simulation result equals `has_access` per operation.

Run via `scripts/test_module.sh`, then Playwright on :8070: dashboard renders, lock blocks an action,
download appears in Print Log and re-downloads.

## Build order

1. Stale-days setting (~20 min)
2. Print Log (~1 h)
3. Access Lock (~1.5 h)
4. Page tracking + model usage (~1 h)
5. Simulation, read-only (~45 min)
6. Dashboard (~1.5 h)

## Out of scope (later)

- Granting/removing rights from Simulation.
- Locking `type="action"` buttons (they open actions, not model methods).
- Watermarking copies on the PDF.
