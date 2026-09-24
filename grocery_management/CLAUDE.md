# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Mentor mode

See `~/.claude/CLAUDE.md` (user-level) — mentor-mode teaching instructions apply here and to all other Odoo projects.

## What this is

An Odoo 17-style custom addon (`grocery_management`) implementing a small grocery POS/back-office: products, customers, and sales with lines. It depends on `base`, `sale`, `stock`, and `mail` (manifest: [__manifest__.py](__manifest__.py)).

## Running the addon

The addon lives under the Odoo server's addons path alongside `enterprise` and core `addons` (see `/home/hithesh/odoo/odoo/odoo.conf`). There is no dedicated per-project venv/config in this repo — use the shared Odoo checkout at `/home/hithesh/odoo/odoo`.

Start the server with this addon loaded (from `/home/hithesh/odoo/odoo`):
```bash
./venv/bin/python odoo-bin -c odoo.conf -d <database_name> -u grocery_management
```
- `-u grocery_management` upgrades/reloads the module — required after changing models, views, security, or data files.
- `-i grocery_management` instead of `-u` for a first-time install on a fresh database.
- Drop `-u`/`-i` for a plain server start once installed.

There are no automated tests in this addon currently (no `tests/` directory). Verify changes by starting the server and using the Odoo UI, or via `odoo-bin shell -c odoo.conf -d <database_name>` for ORM-level checks.

Python bytecode caches (`__pycache__/*.pyc`) are checked into the working tree but gitignored — don't worry about them.

## Architecture

**Models** (`models/`), all registered via `models/__init__.py`:
- `grocery.product` ([grocery_product.py](models/grocery_product.py)) — product catalog with a computed, searchable `is_low_stock` flag. The low-stock threshold is not hardcoded: it's read from `ir.config_parameter` (key `grocery_management.low_stock_threshold`) via `_get_low_stock_threshold()`, and is user-configurable through Settings.
- `grocery.customer` ([grocery_customer.py](models/grocery_customer.py)) — customers with a sequence-generated `customer_id` (prefix `CUST`, see `data/grocery_sequence.xml`).
- `grocery.sale` ([grocery_sale.py](models/grocery_sale.py)) — the sale header. Inherits `mail.thread` + `mail.activity.mixin` for chatter/activity tracking. Key behaviors:
  - `name` is sequence-generated (prefix `SALE`) in an overridden `create()`.
  - `amount_total` and `low_stock_warning` are compute fields depending on `line_ids` (see line model below).
  - Stock is deducted only on transition to `state == "approved"`, via `_deduct_stock_for_approval()`, called from both the overridden `create()` (if created already-approved) and `write()` (on approval transition). This raises `UserError` if stock is insufficient — approval is the single control point for stock deduction, don't bypass it by writing to product quantities directly elsewhere.
- `grocery.sale.line` ([grocery_sale_line.py](models/grocery_sale_line.py)) — sale line items with a computed `total` (`quantity * price`, stored) and an `@api.onchange("product_id")` that defaults quantity/price from the product.
- `res.config.settings` ([res_config_settings.py](models/res_config_settings.py)) — extends core settings (`TransientModel`, `_inherit`) to add the `grocery_low_stock_threshold` field, backed by the `ir.config_parameter` key referenced above.

**Security** ([security/ir.access.csv](security/ir.access.csv)): flat CRUD access for `base.group_user` on all four models. No record rules or restricted groups defined yet — anyone with basic user access has full CRUD.

**Data** ([data/grocery_sequence.xml](data/grocery_sequence.xml)): `ir.sequence` records for sale (`SALE`) and customer (`CUST`) reference numbers, consumed via `next_by_code()`.

**Views** (`views/`): standard list/form views per model plus a dedicated product menu entry. Loaded order in the manifest matters — security CSV first, then views, then data.

## Conventions observed in this codebase

- Stock quantity is a plain `Float` on `grocery.product`, mutated directly in Python (`product.quantity -= required_qty`) rather than through `stock` module moves/quants, despite `stock` being a manifest dependency — treat this as the existing pattern rather than introducing partial `stock.move` integration without discussing it first.
- Config-driven thresholds go through `ir.config_parameter` + `res.config.settings`, not hardcoded constants — follow this pattern for any other configurable business rule (see the low-stock threshold implementation).
- `@api.model_create_multi` + looping over `vals_list` is the established pattern for overriding `create()` in this codebase (used in both `grocery.sale` and `grocery.customer`).
