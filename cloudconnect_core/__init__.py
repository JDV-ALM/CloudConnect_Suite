# -*- coding: utf-8 -*-

from . import models
from . import services
from . import wizards
from . import controllers

def post_init_hook(env):
    """Post-installation hook to set up initial configuration."""
    # Create default configuration if none exists
    Config = env['cloudconnect.config']
    if not Config.search([]):
        Config.create({
            'name': 'Default Configuration',
            'api_endpoint': 'https://hotels.cloudbeds.com/api/v1.2',
            'active': False,
        })