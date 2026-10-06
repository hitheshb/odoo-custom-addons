# user_access_management: design

## Goal
Let an administrator see and edit, in one place, what each user can access, with two-way drill-down between users, groups and access rights, and a viewable log of every change.

## Decisions (agreed)
- No mirror tables. Screens are views over `res.users`, `res.groups`, `ir.access`. Edits write to the real records.
- New module `user_access_management`, `depends: ['base']`. Independent of `access_management`.
- Log captures every change to those records, from any source (these screens, standard forms, import, scripts).
- Administrators only (`base.group_system`).

## Odoo 20 facts (verified in source)
- `res.groups`: `user_ids`, `all_user_ids`, `implied_ids`, `all_implied_ids`, `implied_by_ids`, `all_implied_by_ids`, `access_ids` (One2many to `ir.access`), `privilege_id`.
- `res.users`: `group_ids`, `all_group_ids`.
- `ir.access`: `name`, `model_id`, `group_id`, `operation` (crud subset), `domain`, `kind`. CSV file is `security/ir.access.csv`.

## Components
1. **Model `access.change.log`** (one concern per file)
   - Fields: `date`, `acting_user_id` (who made the change), `action` (add / remove / create / edit / delete), `target_kind` (user / group / access), `target_name` (text), `field_label` (text), `old_value` (text), `new_value` (text), optional `target_ref` (`Reference`, nullable).
   - Names stored as text so entries survive deletion of the target.
   - Read-only in the UI. Create is internal only (sudo from the overrides); no UI create, write or delete.
2. **Logging overrides** (inheritance only, never edit core)
   - `res.users`: override core hook `_log_group_changes` (called by core from both `res.users.write` and `res.groups.write(user_ids)`, so each change is logged once) and `create`.
   - `res.groups`: `write` for `user_ids` and `implied_ids`; `create` and `unlink`.
   - `ir.access`: `create`, `write` and `unlink`; log old and new `operation`, `domain`, `group_id`, `model_id`.
   - Each override computes old and new values, calls `super()`, then writes log rows. A change is logged on the side that was written, so it is not duplicated.
3. **Screens** (one root menu, administrators only)
   - Users: list and form. Editable direct groups; read-only effective groups (`all_group_ids`); combined access rows (computed through `all_group_ids.access_ids`).
   - Groups: form with users, implied groups, groups that imply this one, access rows. Clickable.
   - Access rights: list with group, plus a smart button listing users who receive it through the group (`group_id.all_user_ids`).
   - Change log: list, filter and group by action, target kind, acting user, date.
4. **Drill-down:** every user, group and access row opens its own record. Smart buttons show counts.

## Security
- `ir.access.csv`: `base.group_system` only on `access.change.log` (read), menus and views carry `groups="base.group_system"`.
- Log rows cannot be edited or deleted from the UI.

## Known limits
- Adding an implied group makes Odoo add it to the group's users automatically. Only the direct edit is logged. The entry notes that implied users were also affected.
- Changes made by direct SQL are not logged.
- Changes made while loading module data (`install_mode` context) are not logged, to avoid noise on every install and upgrade.
- `ir.access` rows with an external ID are read-only in the form (Odoo's own rule); custom rows are editable.
- Log rows are written with sudo; they record the real acting user (`self.env.user`), not the sudo user.

## Testing
- Add and remove a group on a user: one log row each, correct old and new values.
- Edit `implied_ids` on a group: logged once.
- Create, edit and delete an `ir.access` row: three log rows; deleting leaves the log row readable.
- A non-admin user cannot open the menus or read the log.
- Drill-down: group form lists exactly `all_user_ids`; access smart button lists exactly `group_id.all_user_ids`.
