from collections import defaultdict    # used to create dict with missing keys set default to 0
from odoo import api, fields, models    #standard everywhere
from odoo.exceptions import UserError   # stops user and gives error used in 80

# class begins here
class GrocerySale(models.Model):
    _name = "grocery.sale"
    _description = "Grocery Sale"
    _inherit = ["mail.thread", "mail.activity.mixin", "grocery.sequence.mixin"]

    _sequence_code = "grocery.sale"     # mixin config: see grocery_sequence_mixin.py

# FIELDS 
    name = fields.Char(
        string="Sale Reference",
        required=True,
        default="New",
        readonly=True,
        copy=False,
    )

    customer_id = fields.Many2one(
        "grocery.customer",
        string="Customer",
        required=True
    )

    sale_date = fields.Datetime(string="Sale Date")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("approved", "Approved"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
    )

    line_ids = fields.One2many(
        "grocery.sale.line",
        "sale_id",
        string="Sale Lines"
    )

    amount_total = fields.Float(
        string="Total",
        compute="_compute_amount_total",     # can call it as compute field
        store=True
    )

    low_stock_warning = fields.Char(
        string="Low Stock Warning",
        compute="_compute_low_stock_warning",
    )

    discount_selection = fields.Selection(
        [
            ("regular", "Regular Customer - 5%"),
            ("wholesale", "Whole Sale - 10%"),
        ],
        string="Discount Type",
        help="Choose a tier to auto-fill the discount rate below via onchange.",
    )

    discount_rate = fields.Float(
        string="Discount Rate (%)",
        readonly=True,          # plain field, NOT compute= -> only the onchange below sets it
    )
# FIELDS END HERE

# ONCHANGE TO SET DISCOUNT RATE BASED ON DISCOUNT SELECTION (force_save demo)
    @api.onchange("discount_selection")
    def _onchange_discount_selection(self):
        rates = {"regular": 5.0, "wholesale": 10.0}
        self.discount_rate = rates.get(self.discount_selection, 0.0)

# COMPUTE FIELD TO FIND TOTAL AMOUNT
    @api.depends("line_ids.total")          # one2many relation to sale.line
    def _compute_amount_total(self):
        for sale in self:
            sale.amount_total = sum(sale.line_ids.mapped("total"))  # comverts to list  from each line and sums them

# COMPUTE FIELD FOR LOW STOCK WARNING MESSAGE. (Before saving)
    @api.depends("line_ids.product_id", "line_ids.quantity")  #computes when product or quantity changes
    def _compute_low_stock_warning(self):
        for sale in self:
            messages = []
            for line in sale.line_ids:
                if line.product_id and line.product_id.quantity < line.quantity:
                    messages.append(
                        "Only %s units left for %s (need %s)."
                        % (line.product_id.quantity, line.product_id.name, line.quantity)
                    )
            sale.low_stock_warning = "\n".join(messages)


# FUNCTION FOR LOW STOCK WARNING (After saving)
    def _deduct_stock_for_approval(self, sales):                                      # deducts items after saving the sale.
        required_by_product = defaultdict(float)
        for sale in sales:
            for line in sale.line_ids:
                required_by_product[line.product_id] += line.quantity

        for product, required_qty in required_by_product.items():
            if product.quantity < required_qty:
                raise UserError(
                    "Not enough units available for %s. "
                    "Available: %s, Required: %s."
                    % (product.name, product.quantity, required_qty)
                )

        for product, required_qty in required_by_product.items():
            product.quantity -= required_qty

# FUNCTION FOR WHEN STATUSBAR IS SET TO APPROVED
    def write(self, vals):
        if vals.get("state") == "approved":
            sales_to_approve = self.filtered(lambda s: s.state != "approved")
            res = super().write(vals)
            self._deduct_stock_for_approval(sales_to_approve)                       #call above def to deduct in shelf
            return res

        return super().write(vals)

# TO OVERRIDE CREATE FUNCTION AND TO ADD SEQUENCE
    @api.model_create_multi
    def create(self, vals_list):
        self._assign_sequence_numbers(vals_list)

        sales = super().create(vals_list)

        approved_sales = sales.filtered(lambda s: s.state == "approved")
        if approved_sales:
            self._deduct_stock_for_approval(approved_sales)                       # calls above def when approved is given at the beginning itself

        return sales

# SERVER ACTION TARGET (see data/grocery_automation.xml) - bound to the Sales list's Action menu.
# Just calls write() on the whole recordset so the override above still owns stock deduction.
    def action_bulk_approve(self):
        self.write({"state": "approved"})