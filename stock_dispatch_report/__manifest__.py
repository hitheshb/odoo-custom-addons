{
    'name': 'Stock Dispatch Report',
    'version': '1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Read-only dispatch report built on stock moves',
    'author': 'Hithesh',
    # 'stock' provides stock_move / stock_picking. 'sale_stock' is what adds
    # the sale_line_id column to stock_move, which this view reads.
    'depends': ['stock', 'sale_stock'],
    'data': [
        'security/ir.access.csv',
        'views/stock_dispatch_report_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
