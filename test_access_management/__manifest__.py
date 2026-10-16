{
    'name': 'Test Access Management',
    'version': '20.0.1.0.0',
    'summary': 'Complete reference build of Access Management (profiles, sync, xlsx export/upload)',
    'category': 'Administration',
    'depends': ['base'],
    'data': [
        'security/ir.access.csv',
        'views/access_profile_views.xml',
        'views/res_users_views.xml',
        'wizard/profile_upload_views.xml',
        'wizard/access_import_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': ['test_access_management/static/src/profile_users_field.js'],
    },
    'license': 'LGPL-3',
    'application': True,
    'installable': True,
}
