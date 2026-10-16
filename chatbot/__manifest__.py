{
    'name': 'Chatbot',
    'version': '20.0.1.0.0',
    'summary': 'A chat panel on every screen that reads and writes Odoo records for you',
    'category': 'Productivity',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.access.csv',
        'views/res_config_settings_views.xml',
        'views/chatbot_message_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'chatbot/static/src/chatbot/*',
        ],
    },
    'license': 'LGPL-3',
    'application': False,
    'installable': True,
}
