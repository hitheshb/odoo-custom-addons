from odoo import fields, models
from odoo.tools.sql import column_exists, drop_view_if_exists


class SaleDispatchReport(models.Model):
    _name = 'sale.dispatch.report'
    _description = 'Sales Dispatch Report'
    _auto = False
    _rec_name = 'product_id'
    _order = 'scheduled_date desc, id desc'

    # --- from product_product / product_template ---
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    default_code = fields.Char(string='Internal Reference', readonly=True)
    hsn_code = fields.Char(string='HSN/SAC', readonly=True)

    # --- from sale_order_line ---
    product_uom_qty = fields.Float(string='Qty', digits='Product Unit', readonly=True)
    qty_delivered = fields.Float(string='Delivered', digits='Product Unit', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', readonly=True)

    # --- aggregated from stock_move / stock_picking ---
    total_demand = fields.Float(string='Total Demand', digits='Product Unit', readonly=True)
    scheduled_date = fields.Datetime(string='Scheduled Date', readonly=True)

    # --- from sale_order ---
    fiscal_position_id = fields.Many2one(
        'account.fiscal.position', string='Fiscal Position', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    order_id = fields.Many2one('sale.order', string='Order', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)

    def init(self):
        # HSN/SAC lives on product_template, but only once l10n_in (Indian
        # localization) is installed. Degrade to a blank column instead of
        # hard-depending on the whole localization for one field.
        hsn = (
            'pt.l10n_in_hsn_code'
            if column_exists(self.env.cr, 'product_template', 'l10n_in_hsn_code')
            else 'NULL::varchar'
        )
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE VIEW {self._table} AS (
                SELECT
                    sol.id                                      AS id,
                    sol.order_id                                AS order_id,
                    so.partner_id                               AS partner_id,
                    so.company_id                               AS company_id,
                    sol.product_id                              AS product_id,
                    COALESCE(pp.default_code, pt.default_code)  AS default_code,
                    {hsn}                                       AS hsn_code,
                    sol.product_uom_qty                         AS product_uom_qty,
                    sol.qty_delivered                           AS qty_delivered,
                    sol.product_uom_id                          AS uom_id,
                    so.fiscal_position_id                       AS fiscal_position_id,
                    COALESCE(mv.total_demand, 0.0)              AS total_demand,
                    mv.scheduled_date                           AS scheduled_date
                FROM sale_order_line sol
                    JOIN sale_order       so ON so.id = sol.order_id
                    JOIN product_product  pp ON pp.id = sol.product_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    LEFT JOIN (
                        SELECT
                            sm.sale_line_id                           AS sale_line_id,
                            SUM(sm.product_uom_qty)                   AS total_demand,
                            MIN(COALESCE(sp.scheduled_date, sm.date)) AS scheduled_date
                        FROM stock_move sm
                            LEFT JOIN stock_picking sp ON sp.id = sm.picking_id
                        WHERE sm.sale_line_id IS NOT NULL
                          AND sm.state != 'cancel'
                        GROUP BY sm.sale_line_id
                    ) mv ON mv.sale_line_id = sol.id
                WHERE sol.display_type IS NULL
            )
        """)
