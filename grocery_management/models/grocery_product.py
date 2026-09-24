from datetime import timedelta

from odoo import api, fields, models                        # default for all
from odoo.exceptions import ValidationError                 # used with @api.constrains


class GroceryProduct(models.Model):                         # a permanent model
    _name = "grocery.product"                               # odoo model attribute to set technical name
    _description = "Grocery Product"                        # human readable lable in setting/technical/models list
    _inherit = ["mail.thread"]                               # chatter, so the expiry cron below can log messages

# fields
    name = fields.Char(string="Product Name", required=True)
    brand = fields.Char(string="Brand Name")
    category = fields.Char(string="Category")
    cost_price = fields.Float(string="Cost Price")
    selling_price = fields.Float(string="Selling Price", required=True)
    quantity = fields.Float(
        string="Quantity",
        help="Units currently in stock. Drives the Low Stock flag once below the configured threshold.",
    )
    quality = fields.Selection(
        [
            ("0", "0"),
            ("1", "1"),
            ("2", "2"),
            ("3", "3"),
            ("4", "4"),
            ("5", "5"),
        ],
        string="Quality",
        default="0",
    )
    expiry_date = fields.Date(
        string="Expiry Date",
        help="Used by the daily expiry check to warn on products nearing or past this date.",
    )

    is_low_stock = fields.Boolean(
        string="Low Stock",
        compute="_compute_is_low_stock",
        search="_search_is_low_stock",
    )

# COMPUTE FIELD FOR LOW STOCK FLAG (threshold is configurable in Settings)
    @api.depends("quantity")
    def _compute_is_low_stock(self):
        threshold = self._get_low_stock_threshold()
        for product in self:
            product.is_low_stock = product.quantity < threshold

# LETS "Low Stock" FILTER/RIBBON SEARCH BY THE FLAG INSTEAD OF A HARDCODED NUMBER
    def _search_is_low_stock(self, operator, value):
        threshold = self._get_low_stock_threshold()
        wants_low_stock = (operator == "=" and value) or (operator == "!=" and not value)
        comparator = "<" if wants_low_stock else ">="
        return [("quantity", comparator, threshold)]

    def _get_low_stock_threshold(self):
        return self.env["ir.config_parameter"].sudo().get_int(
            "grocery_management.low_stock_threshold", 10
        )

# SAME CONFIG-PARAMETER PATTERN AS THE LOW STOCK THRESHOLD, FOR THE EXPIRY CHECK BELOW
    def _get_expiry_warning_days(self):
        return self.env["ir.config_parameter"].sudo().get_int(
            "grocery_management.expiry_warning_days", 3
        )

# SCHEDULED ACTION TARGET (see data/grocery_automation.xml, runs daily).
# Posts a chatter message on any product that is already expired or expiring soon.
    def _cron_check_expiring_products(self):
        today = fields.Date.context_today(self)
        warning_days = self._get_expiry_warning_days()
        limit_date = today + timedelta(days=warning_days)

        expiring = self.search([
            ("expiry_date", "!=", False),
            ("expiry_date", "<=", limit_date),
        ])
        for product in expiring:
            status = "expired" if product.expiry_date < today else "expiring soon"
            product.message_post(
                body="%s (expiry date: %s) is %s." % (product.name, product.expiry_date, status)
            )