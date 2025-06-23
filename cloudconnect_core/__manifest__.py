# -*- coding: utf-8 -*-
{
    'name': 'CloudConnect Core',
    'version': '17.0.1.0.0',
    'category': 'Hospitality',
    'summary': 'Core module for Cloudbeds PMS integration',
    'description': """
CloudConnect Core Module
========================

Base module for CloudConnect suite providing:
- OAuth 2.0 authentication with Cloudbeds
- Centralized configuration
- Webhook management
- Synchronization engine
- Shared services and utilities

This module serves as the foundation for all CloudConnect extension modules.
    """,
    'author': 'CloudConnect',
    'website': 'https://www.cloudconnect.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'mail',
    ],
    'data': [
        # Security
        'security/cloudconnect_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/ir_cron_data.xml',
        
        # Wizards
        'wizards/cloudconnect_setup_wizard_views.xml',
        
        # Views
        'views/cloudconnect_config_views.xml',
        'views/cloudconnect_property_views.xml',
        'views/cloudconnect_webhook_views.xml',
        'views/cloudconnect_sync_log_views.xml',
        'views/cloudconnect_dashboard_views.xml',
        'views/cloudconnect_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'cloudconnect_core/static/src/js/dashboard.js',
            'cloudconnect_core/static/src/css/dashboard.css',
        ],
    },
    'images': [
        'static/description/icon.png',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}