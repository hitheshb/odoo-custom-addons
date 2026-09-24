from odoo import models


class GrocerySequenceMixin(models.AbstractModel):
    # AbstractModel: never has its own table, only mixed into other models via _inherit.
    # Compare Model (grocery.product - has a table) and TransientModel (wizards - table
    # auto-cleaned by Odoo) - these are the 3 model base classes.
    _name = "grocery.sequence.mixin"
    _description = "Grocery Sequence Numbering Mixin"

    # Override these two on the model that inherits this mixin.
    _sequence_code = None       # ir.sequence code to pull numbers from, e.g. "grocery.sale"
    _sequence_field = "name"    # field the generated number is written into
    _sequence_placeholder = "New"   # value meaning "not assigned yet" (matches a field's default=)

    def _assign_sequence_numbers(self, vals_list):
        """Fill in vals[self._sequence_field] from ir.sequence wherever it's missing.

        Mutates each vals dict in place, mirroring the create() override pattern
        already used across this addon (@api.model_create_multi + loop over vals_list).
        """
        if not self._sequence_code:
            return
        for vals in vals_list:
            current = vals.get(self._sequence_field)
            if not current or current == self._sequence_placeholder:
                vals[self._sequence_field] = self.env["ir.sequence"].next_by_code(self._sequence_code)
