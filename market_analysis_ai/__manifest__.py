{
    'name': 'Market Analysis AI',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Análisis de mercados con OpenAI y Telegram',
    'description': """
        App para recibir reportes de precios de productos vía Telegram
        y procesarlos con OpenAI para análisis de mercados.
    """,
    'author': 'Almus Dev',
    'website': 'https://www.almus.dev',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron_data.xml',
        'views/market_analysis_settings_views.xml',
        'views/market_analysis_report_views.xml',
        'views/menu_views.xml',
    ],
    'external_dependencies': {
        'python': ['openai', 'requests'],
    },
    'requirements': [
        'requirements.txt',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'assets': {
        'web.assets_backend': [
            'market_analysis_ai/static/src/js/password_field.js',
        ],
    },
}