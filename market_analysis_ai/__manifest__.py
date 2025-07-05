{
    'name': 'Market Analysis AI',
    'version': '1.1',
    'category': 'Tools',
    'summary': 'Análisis de mercados con OpenAI/Claude y Telegram',
    'description': """
        App para recibir reportes de precios de productos vía Telegram
        y procesarlos con OpenAI o Claude (Anthropic) para análisis de mercados.
        
        Características:
        - Soporte para OpenAI (GPT-3.5, GPT-4) y Claude (Haiku, Sonnet, Opus)
        - Recepción automática de mensajes desde Telegram
        - Procesamiento inteligente de precios en lenguaje natural
        - Estadísticas y tendencias de precios
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
        'python': ['openai', 'anthropic', 'requests'],
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