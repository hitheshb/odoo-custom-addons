# Odoo Custom Addons

Custom Odoo modules built while learning the framework. Targets **Odoo saas~19.4**.

## Modules

| Module | Type | Summary |
| --- | --- | --- |
| `meditrack` | Application | Hospital patient, doctor and appointment management, with checkups and prescriptions. Depends on `base`, `contacts`. |
| `sale_dispatch_report` | Report | Read-only dispatch report under **Sales → Reporting**. Depends on `sale_stock`. |
| `stock_dispatch_report` | Report | Read-only dispatch report built on stock moves, under **Inventory**. Depends on `stock`, `sale_stock`. |

All modules are LGPL-3.

## Installation

1. Clone this repository into a directory on your Odoo addons path:

   ```bash
   git clone https://github.com/hitheshb/odoo-custom-addons.git
   ```

2. Add the directory to `addons_path` in your Odoo config, or pass it on the
   command line:

   ```bash
   ./odoo-bin --addons-path=addons,/path/to/odoo-custom-addons -d your_db
   ```

3. Restart Odoo, then update the apps list (**Apps → Update Apps List**, with
   developer mode enabled) and install the modules you want.

## Notes

The `grocery_management` module lives in its own repository:
<https://github.com/hitheshb/grocery_management>
