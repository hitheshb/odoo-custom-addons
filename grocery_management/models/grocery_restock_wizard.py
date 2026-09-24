from odoo import fields, models
from odoo.exceptions import UserError


class GroceryRestockWizard(models.TransientModel):
    # TransientModel: rows live in a real table like Model, but Odoo auto-purges old
    # ones (vacuum cron) since this data only matters for the lifetime of the dialog.
    _name = "grocery.restock.wizard"
    _description = "Restock Product"

    product_id = fields.Many2one("grocery.product", string="Product", required=True)
    current_quantity = fields.Float(related="product_id.quantity", string="Current Quantity", readonly=True)
    quantity_to_add = fields.Float(string="Quantity to Add", required=True, default=1)

    def action_confirm(self):
        self.ensure_one()
        if self.quantity_to_add <= 0:
            raise UserError("Quantity to add must be greater than zero.")

        self.product_id.quantity += self.quantity_to_add
        self.product_id.message_post(
            body="Restocked %s units (new quantity: %s)."
            % (self.quantity_to_add, self.product_id.quantity)
        )
