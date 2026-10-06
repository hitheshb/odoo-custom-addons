{
    'name': 'User Access Management',
    'version': '20.0.1.0.0',
    'summary': 'See and edit what users, groups and access rights give, with a change log',
    'category': 'Administration',
    'depends': ['base'],
    'data': [
        'security/ir.access.csv',
        'views/access_change_log_views.xml',
        'views/access_views.xml',
        'views/group_views.xml',
        'views/user_views.xml',
        'views/menus.xml',
    ],
    'license': 'LGPL-3',
    'application': True,
    'installable': True,
}
