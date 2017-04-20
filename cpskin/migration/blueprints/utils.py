# -*- coding: utf-8 -*-
from zope.annotation.interfaces import IAnnotations


BATCH_CURRENT_KEY = 'cpskin.core.migration.blueprints:batch_current'
BATCH_SIZE_KEY = 'cpskin.core.migration.blueprints:batch_size'
TOTAL_OBJECTS_KEY = 'cpskin.core.migration.blueprints:total_objects'


def is_first_transmo(portal):
    anno = IAnnotations(portal)
    batch_current = anno[BATCH_CURRENT_KEY]
    return batch_current == 0


def is_last_transmo(portal):
    anno = IAnnotations(portal)
    batch_current = int(anno[BATCH_CURRENT_KEY])
    batch_size = int(anno[BATCH_SIZE_KEY])
    total_objects = int(anno[TOTAL_OBJECTS_KEY])
    return (total_objects - batch_current) < batch_size
