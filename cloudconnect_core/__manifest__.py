# -*- coding: utf-8 -*-
{
    'name': 'CloudConnect Core',
    'version': '17.0.1.0.0',
    'category': 'Hospitality',
    'summary': 'Core module for Cloudbeds PMS integration',
    'description': """
CloudConnect Core
=================

This is the base module for the CloudConnect suite that provides infrastructure
for integrating with Cloudbeds PMS, including:

- OAuth 2.0 authentication with Cloudbeds
- Centralized configuration management
- Webhook processing and validation
- API rate limiting and retry logic
- Sync logging and monitoring
- Property and timezone management

Required for all other CloudConnect modules.
    """,
    'author': 'CloudConnect Team',
    'website': 'https://www.cloudconnect.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
    ],
    'external_dependencies': {
        'python': ['requests', 'cryptography'],
    },
    'data': [
        # Security
        'security/cloudconnect_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/cloudconnect_cron_jobs.xml',
        
        # Views
        'views/cloudconnect_menus.xml',
        'views/cloudconnect_config_views.xml',
        'views/cloudconnect_property_views.xml',
        'views/cloudconnect_webhook_views.xml',
        'views/cloudconnect_sync_log_views.xml',
        'views/cloudconnect_dashboard_views.xml',
        
        # Wizards
        'wizards/setup_wizard_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    'sequence': 1,
    'post_init_hook': 'post_init_hook',
}