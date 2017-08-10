# -*- coding: utf-8 -*-
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.utils import defaultMatcher
from collective.transmogrifier.utils import Expression
from OFS.interfaces import IItem
from plone.app.textfield.interfaces import IRichText
from plone.dexterity.interfaces import IDexterityContent
from plone.dexterity.utils import iterSchemata
from plone.uuid.interfaces import IMutableUUID
from Products.Archetypes.event import ObjectEditedEvent
from Products.Archetypes.event import ObjectInitializedEvent
from Products.Archetypes.interfaces import IBaseObject
from transmogrify.dexterity.interfaces import IDeserializer
from z3c.form import interfaces
from zope import event
from zope.component import getMultiAdapter
from zope.component import queryMultiAdapter
from zope.component.hooks import getSite
from zope.event import notify
from zope.interface import classProvides
from zope.interface import implementer
from zope.lifecycleevent import ObjectModifiedEvent
from zope.schema import getFieldsInOrder

import logging
import sys


logger = logging.getLogger('Cpskin blueprints schemaupdater')
logger.setLevel(logging.INFO)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s',
                              '%Y-%m-%d %H:%M:%S')
ch.setFormatter(formatter)
logger.addHandler(ch)

_marker = object()


def _compare(fieldval, itemval):
    """Compare a AT Field value with an item value
    Because AT fields return utf8 instead of unicode and item values may be
    unicode, we need to special-case this comparison. In case of fieldval
    being a str and itemval being a unicode value, we'll decode fieldval and
    assume utf8 for the comparison.
    """
    if isinstance(fieldval, str) and isinstance(itemval, unicode):
        return fieldval.decode('utf8', 'replace') == itemval
    return fieldval == itemval


def get(field, obj):
    if getattr(field, 'getAccessor', False):
        return field.getAccessor(obj)()
    elif field.accessor is not None:
        return getattr(obj, field.accessor)()
    return field.get(obj)


def set(field, obj, val):
    if getattr(field, 'getMutator', False):
        field.getMutator(obj)(val)
    elif field.mutator is not None:
        getattr(obj, field.mutator)(val)
    else:
        field.set(obj, val)


@implementer(ISection)
class DexterityUpdateSection(object):
    classProvides(ISectionBlueprint)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.context = transmogrifier.context if transmogrifier.context else getSite()  # noqa
        self.name = name
        self.pathkey = defaultMatcher(options, 'path-key', name, 'path')
        self.fileskey = options.get('files-key', '_files').strip()
        self.disable_constraints = Expression(
            options.get('disable-constraints', 'python: False'),
            transmogrifier,
            name,
            options,
        )

        # if importing from collective.jsonify exported json structures, there
        # is an datafield entry for binary data, which' prefix can be
        # configured.
        self.datafield_prefix = options.get('datafield-prefix', '_datafield_')

        # create logger
        if options.get('logger'):
            self.logger = logging.getLogger(options['logger'])
            self.loglevel = getattr(logging, options['loglevel'], None)
            if self.loglevel is None:
                # Assume it's an integer:
                self.loglevel = int(options['loglevel'])
            self.logger.setLevel(self.loglevel)
            self.log = lambda s: self.logger.log(self.loglevel, s)
        else:
            self.log = None

    def get_value_from_pipeline(self, field, item):
        name = field.getName()
        # setting value from the blueprint cue
        value = item.get(name, _marker)
        if value is _marker:
            # Also try _datafield_FIELDNAME structure from jsonify
            value = item.get('_datafield_%s' % name, _marker)
            # try to get leadImage
            if value is _marker and name == 'image':
                value = item.get('_datafield_leadImage', _marker)
        if value is not _marker:
            # Value was given in pipeline, so set it
            deserializer = IDeserializer(field)
            if IRichText.providedBy(field)\
                    and '_content_type_%s' % name in item:
                # change jsonify structure to one we understand
                value = {
                    'contenttype': item['_content_type_%s' % name],
                    'data': value
                }
            files = item.setdefault(self.fileskey, {})
            if isinstance(value, bool):
                return value
            if value == u'<NO_VALUE>':
                return ''
            value = deserializer(
                value,
                files,
                item,
                self.disable_constraints,
                logger=self.log
            )
        return value

    def determine_default_value(self, obj, field):
        """Determine the default to be set for a field that didn't receive
        a value from the pipeline.
        """
        default = queryMultiAdapter((
            obj,
            obj.REQUEST,  # request
            None,  # form
            field,
            None,  # Widget
        ), interfaces.IValue, name='default')
        if default is not None:
            default = default.get()
        if default is None:
            default = getattr(field, 'default', None)
        if default is None:
            try:
                default = field.missing_value
            except AttributeError:
                pass
        return default

    def update_field(self, obj, field, item):
        if field.readonly:
            return

        name = field.getName()
        try:
            value = self.get_value_from_pipeline(field, item)
        except:
            pass
        if value is not _marker:
            field.set(field.interface(obj), value)
            return

        # Get the field's current value, if it has one then leave it alone
        value = getMultiAdapter(
            (obj, field),
            interfaces.IDataManager).query()

        # Fix default description to be an empty unicode instead of
        # an empty bytestring because of this bug:
        # https://github.com/plone/plone.dexterity/pull/33
        if name == 'description' and value == '':
            field.set(field.interface(obj), u'')
            return

        if not(value is field.missing_value or value is interfaces.NO_VALUE):
            return

        # Finally, set a default value if nothing is set so far
        default = self.determine_default_value(obj, field)
        field.set(field.interface(obj), default)

    def __iter__(self):
        for item in self.previous:
            # start = time.time()
            pathkey = self.pathkey(*item.keys())[0]
            # not enough info
            if not pathkey:
                yield item
                continue

            path = item[pathkey]
            # Skip the Plone site object itself
            if not path:
                yield item
                continue

            obj = self.context.unrestrictedTraverse(
                path.encode().lstrip('/'), None)

            if not IItem.providedBy(obj):
                # Path doesn't exist
                # obj can not only be None, but also the value of an attribute,
                # which is returned by traversal.
                yield item
                continue
            isdx = IDexterityContent.providedBy(obj)
            isat = IBaseObject.providedBy(obj)
            uuid = item.get('plone.uuid')
            if uuid is not None:
                if isdx:
                    IMutableUUID(obj).set(str(uuid))
                if isat:
                    obj._setUID(str(uuid))

            # For all fields in the schema, update in roughly the same way
            # z3c.form.widget.py would
            if isdx:
                for schemata in iterSchemata(obj):
                    for name, field in getFieldsInOrder(schemata):
                        self.update_field(obj, field, item)
                notify(ObjectModifiedEvent(obj))
            if isat:
                changed = False
                is_new_object = obj.checkCreationFlag()
                for k, v in item.iteritems():
                    if k.startswith('_'):
                        continue
                    field = obj.getField(k)
                    if field is None:
                        continue
                    if not _compare(get(field, obj), v):
                        set(field, obj, v)
                        changed = True
                obj.unmarkCreationFlag()

                if is_new_object:
                    event.notify(ObjectInitializedEvent(obj))
                    obj.at_post_create_script()
                elif changed:
                    event.notify(ObjectEditedEvent(obj))
                    obj.at_post_edit_script()

            yield item
