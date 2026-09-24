from odoo import api, fields, models


class GrocerySaleLine(models.Model):
    _name = "grocery.sale.line"
    _description = "Grocery Sale Line"

    sale_id = fields.Many2one(
        "grocery.sale",
        string="Sale",
        required=True,
        ondelete="cascade",
    )

    product_id = fields.Many2one(
        "grocery.product",
        string="Product",
        required=True
    )

    quantity = fields.Float(
        string="Quantity",
        required=True,
        default=1
    )

    price = fields.Float(
        string="Price",
        required=True
    )

    total = fields.Float(
        string="Total",
        compute="_compute_total",
        store=True
    )

    @api.depends("quantity", "price")
    def _compute_total(self):
        for line in self:
            line.total = line.quantity * line.price

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.quantity = 1
            self.price = self.product_id.selling_price