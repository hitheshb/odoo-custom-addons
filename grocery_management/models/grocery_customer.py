from odoo import fields, models, api

# class Model
class GroceryCustomer(models.Model):
    _name = "grocery.customer"          # Technical name
    _description = "Grocery Customer"
    _inherit = ["grocery.sequence.mixin"]     # AbstractModel mixin - see grocery_sequence_mixin.py

    _sequence_code = "grocery.customer"       # mixin config: which ir.sequence to draw from
    _sequence_field = "customer_id"           # mixin config: which field gets the generated number

# FIELDS
    name = fields.Char(string="Customer Name", required=True)
    phone = fields.Char(string="Phone")
    email = fields.Char(string="Email")
    address = fields.Text(string="Address")
    customer_id = fields.Char(string="Customer ID",readonly=True,copy=False)

    sale_ids = fields.One2many("grocery.sale", "customer_id", string="Sales")
    sale_count = fields.Integer(string="Sale Count", compute="_compute_sale_count")

# CREATE SEQUENCE FOR CUSTOMER USING CUSTOMER ID FIELD
# LINKED TO GROCERY_SEQUENCE.XML
# TWO WAYS, 1)next by code 2)next by id
    @api.model_create_multi
    def create(self, vals_list):
        self._assign_sequence_numbers(vals_list)
        return super().create(vals_list)

# COMPUTE FIELD FOR THE SMART BUTTON ON THE FORM (button box)
    @api.depends("sale_ids")
    def _compute_sale_count(self):
        for customer in self:
            customer.sale_count = len(customer.sale_ids)

# CALLED BY THE SMART BUTTON: reuses the existing Sales action, scoped to this customer
    def action_view_sales(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("grocery_management.action_grocery_sale")
        action["domain"] = [("customer_id", "=", self.id)]
        action["context"] = {"default_customer_id": self.id}
        return action