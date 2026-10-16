{
    'name': 'Test Administration',
    'version': '20.0.1.0.0',
    'summary': 'Admin dashboard: activity log, sessions, temporary access and access simulation',
    'category': 'Administration',
    'depends': ['base', 'mail', 'hr', 'hr_attendance'],
    'data': [
        'security/ir.access.csv',
        'views/admin_activity_views.xml',
        'views/admin_views.xml',
        'views/menus.xml',
        'data/ir_cron.xml',
    ],
    'license': 'LGPL-3',
    'application': True,
    'installable': True,
}
