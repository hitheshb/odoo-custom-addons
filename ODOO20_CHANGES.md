# Odoo 20.0 — changes that matter for these addons

Notes from porting these modules from saas~19.4 to 20.0 (2026-09-24).
Everything below was checked against the actual 19.4 and 20.0 source, or tested in `odoo-bin shell`.

## 1. Database upgrades between versions need Odoo's upgrade service

- Code (these modules) you port yourself. **Data** (a database) you can't upgrade offline:
  the 20.0 source ships migration scripts for only 6 modules.
- `-u all` on a copy of the 19.4 database failed inside core modules (a moved state record,
  then `KeyError: 'account.move'`), not in these modules.
- To carry real data across, use https://upgrade.odoo.com (included with Enterprise).
- Always test an upgrade on a **copy** of the database: `-u all` changes it the moment it starts.

## 2. `search=` methods receive normalized operators (since 19.x)

A domain is rewritten before your custom search method is called:

| Domain you write            | What the method receives        |
|-----------------------------|---------------------------------|
| `('is_low_stock', '=', True)`  | `operator='in'`, `value={True}`     |
| `('is_low_stock', '!=', False)`| `operator='in'`, `value={True}`     |
| `('is_low_stock', '=', False)` | `operator='not in'`, `value={True}` |

`value` is a set (`OrderedSet`), not a `bool`. Check for `'in'` / `'not in'`, never `'='` / `'!='`:

```python
wants = (operator == "in") == (True in value)   # bool
```

**Open bug:** `grocery_management/models/grocery_product.py` `_search_is_low_stock` still
checks `'='`/`'!='`, so the Low Stock filter returns nothing on both 19.4 and 20.0.

## 3. Demo data is off by default

New databases get no sample data unless you pass `--with-demo`.

## 4. Minimum versions

- Python **3.12+** (the system `python3` here is 3.10; always use the venv)
- PostgreSQL **16+**

## 5. `odoo-bin upgrade_code` rewrites module source for you

```bash
venv/bin/python odoo-bin upgrade_code --addons-path <this folder> --from 19.4 --dry-run
```

- Preview with `--dry-run` first. The `--from` version is inclusive.
- New in 20.0: `_rec_names_search` should be a tuple, not a list:
  `_rec_names_search = ('name',)`.
- These modules needed no rewrites.

## 6. Still valid in 20.0 (unchanged from 19.4)

- `security/ir.access.csv` and `ir.access` records (`group_id`, `operation`, `domain`)
- `res.groups` with `privilege_id` / `user_ids` and `res.groups.privilege`
- `ir.cron` / `ir.actions.server` XML with `model_id`, `state`, `code`
- `stock.move.uom_id` and `sale.order.line.product_uom_id`, plus every other column the
  three SQL-view reports read
- `odoo.tools.sql.column_exists` and `drop_view_if_exists`. (`pg_varchar` was removed and
  `format_query` was added.)

## 7. Before using these fields, check they still exist

- These are no longer in their 19.4 files (removed or moved; not yet checked):
  - `sale.order.require_payment`
  - `stock.move.show_operations`
- `stock.picking.type` now lives in its own file, not in `stock_picking.py`.

## Local setup

| | 19.4 | 20.0 |
|---|---|---|
| Folder   | `/home/hithesh/odoo/`   | `/home/hithesh/odoo20/` |
| Git branch | `main`                | `20.0` (worktree)       |
| Database | `odoo19`                | `odoo20` (fresh, demo data) |
| Port     | 8069                    | 8070                    |

Run 20.0:

```bash
cd /home/hithesh/odoo20/odoo
venv/bin/python odoo-bin -c odoo.conf -d odoo20 -u <module>
```
