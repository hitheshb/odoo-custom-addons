from odoo import fields, models
from odoo.tools.sql import column_exists, drop_view_if_exists


class StockDispatchReport(models.Model):
    _name = 'stock.dispatch.report'
    _description = 'Stock Dispatch Report'
    _auto = False
    _rec_name = 'product_id'
    _order = 'scheduled_date desc, id desc'

    # --- from stock_move ---
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', readonly=True)
    product_uom_qty = fields.Float(string='Demand', digits='Product Unit', readonly=True)
    quantity = fields.Float(string='Quantity', digits='Product Unit', readonly=True)
    qty_done = fields.Float(string='Done', digits='Product Unit', readonly=True)
    picked = fields.Boolean(string='Picked', readonly=True)
    state = fields.Selection([
        ('draft', 'New'),
        ('waiting', 'Waiting Another Move'),
        ('confirmed', 'Waiting'),
        ('partially_available', 'Partially Available'),
        ('assigned', 'Available'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True)
    date = fields.Datetime(string='Date Scheduled', readonly=True)
    date_deadline = fields.Datetime(string='Deadline', readonly=True)
    reference = fields.Char(string='Reference', readonly=True)
    origin = fields.Char(string='Source Document', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    # --- from stock_location ---
    location_id = fields.Many2one('stock.location', string='From', readonly=True)
    location_dest_id = fields.Many2one('stock.location', string='To', readonly=True)

    # --- from stock_picking / stock_picking_type ---
    picking_id = fields.Many2one('stock.picking', string='Transfer', readonly=True)
    picking_type_id = fields.Many2one(
        'stock.picking.type', string='Operation Type', readonly=True)
    # 'mrp_operation' is added to stock.picking.type.code by the mrp module
    # via selection_add. This report does not inherit that model, so the value
    # is listed explicitly; without it manufacturing moves show a blank type.
    picking_code = fields.Selection([
        ('incoming', 'Receipt'),
        ('outgoing', 'Delivery'),
        ('internal', 'Internal Transfer'),
        ('mrp_operation', 'Manufacturing'),
    ], string='Type of Operation', readonly=True)
    scheduled_date = fields.Datetime(string='Scheduled Date', readonly=True)
    date_done = fields.Datetime(string='Date of Transfer', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)

    # --- from product_product / product_template ---
    default_code = fields.Char(string='Internal Reference', readonly=True)
    hsn_code = fields.Char(string='HSN/SAC', readonly=True)
    categ_id = fields.Many2one(
        'product.category', string='Product Category', readonly=True)

    # --- from sale_order_line / sale_order (nullable: non-sale moves) ---
    sale_line_id = fields.Many2one('sale.order.line', string='Sale Line', readonly=True)
    order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    fiscal_position_id = fields.Many2one(
        'account.fiscal.position', string='Fiscal Position', readonly=True)

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
                    sm.id                                       AS id,
                    sm.product_id                               AS product_id,
                    sm.uom_id                                   AS uom_id,
                    sm.product_uom_qty                          AS product_uom_qty,
                    sm.quantity                                 AS quantity,
                    CASE WHEN sm.picked THEN sm.quantity
                         ELSE 0.0 END                           AS qty_done,
                    sm.picked                                   AS picked,
                    sm.state                                    AS state,
                    sm.date                                     AS date,
                    sm.date_deadline                            AS date_deadline,
                    sm.reference                                AS reference,
                    sm.origin                                   AS origin,
                    sm.company_id                               AS company_id,
                    sm.location_id                              AS location_id,
                    sm.location_dest_id                         AS location_dest_id,
                    sm.picking_id                               AS picking_id,
                    sm.picking_type_id                          AS picking_type_id,
                    spt.code                                    AS picking_code,
                    COALESCE(sp.scheduled_date, sm.date)        AS scheduled_date,
                    sp.date_done                                AS date_done,
                    COALESCE(sp.partner_id,
                             sm.partner_id,
                             so.partner_id)                     AS partner_id,
                    COALESCE(pp.default_code, pt.default_code)  AS default_code,
                    {hsn}                                       AS hsn_code,
                    pt.categ_id                                 AS categ_id,
                    sm.sale_line_id                             AS sale_line_id,
                    sol.order_id                                AS order_id,
                    so.fiscal_position_id                       AS fiscal_position_id
                FROM stock_move sm
                    JOIN product_product   pp  ON pp.id  = sm.product_id
                    JOIN product_template  pt  ON pt.id  = pp.product_tmpl_id
                    LEFT JOIN stock_picking      sp  ON sp.id  = sm.picking_id
                    LEFT JOIN stock_picking_type spt ON spt.id = sm.picking_type_id
                    LEFT JOIN sale_order_line    sol ON sol.id = sm.sale_line_id
                    LEFT JOIN sale_order         so  ON so.id  = sol.order_id
            )
        """)
