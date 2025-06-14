# -*- coding: utf-8 -*-

from . import models
from . import services
from . import controllers
from . import wizards

def post_init_hook(cr, registry):
    """Post-initialization hook for CloudConnect Core."""
    # This can be used to set up default configurations
    # or perform initial data setup after module installation
    pass