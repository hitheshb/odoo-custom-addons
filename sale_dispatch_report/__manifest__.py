{
    'name': 'Sales Dispatch Report',
    'version': '1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Read-only dispatch report under Sales > Reporting',
    'author': 'Hithesh',
    'depends': ['sale_stock'],
    'data': [
        'security/ir.access.csv',
        'views/sale_dispatch_report_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
