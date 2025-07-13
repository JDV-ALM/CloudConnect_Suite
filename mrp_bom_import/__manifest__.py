# -*- coding: utf-8 -*-
{
    'name': 'MRP BoM Import',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Import Bill of Materials from CSV files',
    'description': """
        This module allows to import Bill of Materials (BoM) from CSV files.
        Features:
        - Import BoMs with components from CSV
        - Validation of products and quantities
        - Error handling and reporting
    """,
    'author': 'Almus Dev (JDV-ALM)',
    'website': 'https://www.almus.dev',
    'depends': ['mrp'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/mrp_bom_import_wizard_view.xml',
        'data/server_action.xml',
        'data/menu_action.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}