# -*- coding: utf-8 -*-
from collective.contentleadimage.leadimageprefs import ILeadImagePrefsForm
from collective.geo.geographer.interfaces import IGeoreferenceable
from collective.geo.behaviour.behaviour import Coordinates
from collective.geo.geographer.interfaces import IWriteGeoreferenced
from copy import deepcopy

from cpskin.core.interfaces import IAlbumCollection
from cpskin.core.interfaces import IBannerActivated
from cpskin.core.interfaces import IFolderViewSelectedContent
from cpskin.core.interfaces import IFolderViewWithBigImages
from cpskin.core.interfaces import ILocalBannerActivated
from cpskin.core.interfaces import IMediaActivated
from cpskin.core.interfaces import IVideoCollection
from cpskin.core.utils import safe_utf8
from cpskin.core.viewlets.interfaces import IViewletMenuToolsBox
from cpskin.core.viewlets.interfaces import IViewletMenuToolsFaceted
from cpskin.menu.interfaces import IDirectAccess
from cpskin.menu.interfaces import IFourthLevelNavigation

from eea.facetednavigation.criteria.handler import Criteria
from eea.facetednavigation.criteria.interfaces import ICriteria
from eea.facetednavigation.indexes.language.interfaces import ILanguageWidgetAdapter
from eea.facetednavigation.interfaces import IFacetedNavigable
from eea.facetednavigation.settings.interfaces import IDisableSmartFacets
from eea.facetednavigation.settings.interfaces import IHidePloneLeftColumn
from eea.facetednavigation.settings.interfaces import IHidePloneRightColumn
from eea.facetednavigation.subtypes.interfaces import IFacetedWrapper
from eea.facetednavigation.views.interfaces import IViewsInfo
from eea.facetednavigation.widgets.alphabetic.interfaces import IAlphabeticWidget
from eea.facetednavigation.widgets.interfaces import ICriterion
from eea.facetednavigation.widgets.interfaces import IWidget
from eea.facetednavigation.widgets.interfaces import IWidgetsInfo
from eea.facetednavigation.widgets.resultsfilter.interfaces import IResultsFilterWidget
from plone import api
from plone.app.contenttypes.interfaces import IPloneAppContenttypesLayer
from plone.app.contenttypes.migration.migration import ICustomMigrator
from plone.app.event.interfaces import IEventSettings
from plone.app.event.dx.interfaces import IDXEvent
from plone.app.multilingual.interfaces import IPloneAppMultilingualInstalled
from plone.app.textfield.value import RichTextValue
from plone.dexterity.interfaces import IDexterityFTI
from plone.portlets.constants import CONTEXT_BLACKLIST_STATUS_KEY
from plone.portlets.interfaces import IPortletAssignmentMapping
from plone.portlets.interfaces import IPortletManager
from plone.registry.interfaces import IRegistry
from Products.CMFPlone.interfaces.syndication import IFeedSettings
from Products.CMFPlone.interfaces.syndication import ISyndicatable

from z3c.relationfield.event import updateRelations
from z3c.relationfield.interfaces import IHasRelations
from zc.relation.interfaces import ICatalog
from ZODB.POSException import POSKeyError
from zope.annotation.interfaces import IAnnotations
from zope.component import adapter
from zope.component import getMultiAdapter
from zope.component import getUtility
from zope.component import queryUtility
from zope.interface import alsoProvides
from zope.interface import implementer
from zope.interface import Interface
from zope.interface import noLongerProvides


import logging
import uuid

logger = logging.getLogger('cpskin.migration.migrate')
timezone = 'Europe/Brussels'


def migratetodx(context):
    if context.readDataFile('cpskin.migration-migratetodx.txt') is None:
        return
    portal = api.portal.get()
    request = getattr(portal, 'REQUEST', None)
    if is_pam_installed_and_not_used(portal):
        logger.info('Uninstalling PAM')
        ps = api.portal.get_tool(name='portal_setup')
        ps.runAllImportStepsFromProfile(
            'profile-plone.app.multilingual:uninstall')
        noLongerProvides(request, IPloneAppMultilingualInstalled)
    pc = api.portal.get_tool(name='portal_catalog')
    ps = api.portal.get_tool(name='portal_setup')

    # clean up old versionning
    clean_unexisting_objects_in_versionning()
    reindex_relations()

    # clean up old plone.multilingualbehaviors
    remove_old_import_step(ps)
    remove_old_topics()
    # Fix bug, sometimes obj with publish_and_hidden are still in navigation
    set_correctly_exclude_from_nav(pc)

    # Sometimes we have ascii error into text
    fix_transform_errors(portal)

    # fix_dubble_uid()

    logger.info('Starting rebuilding catalog')
    pc.clearFindAndRebuild()

    logger.info('Upgrate to dx')
    logger.info("Installing plone.app.contenttypes")
    ps.runAllImportStepsFromProfile('profile-plone.app.contenttypes:default')
    alsoProvides(request, IPloneAppContenttypesLayer)

    # set view for dexteity content types
    ps.runImportStepFromProfile(
        'profile-cpskin.migration:migratetodx', 'typeinfo')

    logger.info("Enabled cpskin behavior for dx content types")
    enabled_behaviors(portal)

    enabled_leadimage(portal)

    reg = getUtility(IRegistry)
    settings = reg.forInterface(IEventSettings, prefix="plone.app.event")
    if not settings.portal_timezone:
        logger.info('Set timezone to Europe/Brussels')
        settings.portal_timezone = timezone
        settings.first_weekday = 0
        settings.available_timezones = ["Europe/Brussels"]
    # logger.info('install collective.z3cform.widgets')
    # ps.runAllImportStepsFromProfile('profile-collective.z3cform.widgets:default')

    migration_view = getMultiAdapter(
        (portal, request), name=u'migrate_from_atct')
    # call the migration-view above to actually migrate stuff.

    # Do not use plone.memoize cache during migration
    class EmptyMemoize(dict):

        def __setitem__(self, key, value):
            pass

    annotations = IAnnotations(request)
    annotations['plone.memoize'] = EmptyMemoize()

    # for content_type in content_types:
    content_types = [
        'Folder',
        'Collection',
        'Document',
        'Event',
        'File',
        'Image',
        'Link',
        'News Item',
        'BlobFile',
        'BlobImage',
        'Topic',
    ]
    logger.info('Starting migrate {0}'.format(content_types))
    results = migration_view(
        migrate=True,
        content_types=content_types,
        migrate_schemaextended_content=True,
        migrate_references=True,
    )
    logger.info(results)

    logger.info('Fix image scales')
    fix_at_image_scales(portal)
    fix_portlets_image_scales(portal)
    logger.info('collective.contentleadimage uninstallation')
    ps.runAllImportStepsFromProfile(
        'profile-collective.contentleadimage:uninstall')
    logger.info('Apply plonetruegallery step for adding folder view')
    ps.runImportStepFromProfile(
        'profile-collective.plonetruegallery:default', 'typeinfo')
    logger.info('Apply imio.media profile for adding oembed view')
    ps.runImportStepFromProfile('profile-imio.media:default', 'typeinfo')
    logger.info(
        'Apply collecite.geo.leaflet profile for adding geo-leaflet view')
    ps.runImportStepFromProfile(
        'profile-collecite.geo.leaflet:default', 'typeinfo')


def clean_unexisting_objects_in_versionning():
    # Products.CMFEditions.interfaces.IVersioned
    from Products.CMFEditions.interfaces import IVersioned
    catalog = api.portal.get_tool('portal_catalog')
    brains = catalog(object_provides=IVersioned.__identifier__)

    portal = api.portal.get()
    # catalog = api.portal.get_tool('portal_catalog')
    portal_repository = api.portal.get_tool('portal_repository')
    portal_historiesstorage = api.portal.get_tool('portal_historiesstorage')

    # brains = catalog()
    brains_len = len(brains)
    logger.info("{0} objects in portal".format(brains_len))
    thresold = 1000
    j = 0
    for brain in brains:
        try:
            if j % thresold:
                logger.info("{0}/{1} objects".format(j, thresold))
            obj = brain.getObject()
            history = portal_repository.getHistoryMetadata(obj)
            if history:
                length = history.getLength(countPurged=False)
                for i in xrange(length - 1, -1, -1):
                    try:
                        version = portal_repository.retrieve(obj, i)
                        annotations = IAnnotations(version.object)
                        for key in annotations.keys():
                            if key.startswith('collective.alias'):
                                del annotations[key]
                    except POSKeyError:
                        pass
        except KeyError:
            pass

    statistics = portal_historiesstorage.zmi_getStorageStatistics()
    shadowstorage = portal_historiesstorage._getShadowStorage()._storage
    versions_repo = portal_historiesstorage._getZVCRepo()

    # Remove history of deleted objects
    i = 0
    for historyinfo in statistics['deleted']:
        history_id = historyinfo['history_id']
        history = portal_historiesstorage._getShadowHistory(history_id)
        for zvc_key in set([
                portal_historiesstorage._getZVCAccessInfo(
                    history_id, selector, True)[0]
                for selector in history._available]):
            if zvc_key in versions_repo._histories:
                i += 1
                del versions_repo._histories[zvc_key]

    logger.info("{0} history deleted".format(str(i)))
    # and clean :
    #    'CardConfig' from module 'Products.directory.tool.CardConfig'
    #    'Card' from module 'Products.directory.content.Card'
    #    'TTGoogleMap' from module 'tecnoteca.googlemap.content.ttgooglemap'
    #    'TTGoogleMapCategory' from module 'tecnoteca.googlemap.content.ttgooglemapcategory'
    #    'ToolCPSkin' from module 'acptheme.cpskin3.ToolCPSkin'
    #    'Alias' from module 'collective.alias.content'
    #    'ToolDirectory' from module 'Products.directory.tool.ToolDirectory'


def reindex_relations():
    """Clear the relation catalog to fix issues with interfaces that don't exist anymore.
    This actually fixes the from_interfaces_flattened and to_interfaces_flattened indexes.
    """
    rcatalog = getUtility(ICatalog)
    rcatalog.clear()
    catalog = api.portal.get_tool('portal_catalog')
    brains = catalog.searchResults(
        object_provides=IHasRelations.__identifier__)
    for brain in brains:
        obj = brain.getObject()
        updateRelations(obj, None)


def fix_dubble_uid():
    catalog = api.portal.get_tool('portal_catalog')
    uids = []
    for brain in catalog():
        obj = brain.getObject()
        uid = obj.UID()
        if uid not in uids:
            uids.append(uid)
        else:
            if getattr(obj, '_setUID', None):
                newuid = str(uuid.uuid4()).replace('-', '')
                obj._setUID(newuid)
                obj.reindexObject()
                logger.info('Set new uid {}, old was {}'.format(newuid, uid))
            else:
                logger.warning('No _setUID for {}'.format(
                    '/'.join(obj.getPhysicalPath())))


def fix_transform_errors(portal):
    catalog = api.portal.get_tool('portal_catalog')
    # portal_transforms = api.portal.get_tool('portal_transforms')
    for brain in catalog(portal_type=('Document', 'News Item')):
        obj = brain.getObject()
        try:
            obj.getText()
            # data = portal_transforms.convertTo('text/html', text, mimetype='text/-x-web-intelligent')
            # html = data.getData()
        except UnicodeDecodeError:
            api.content.delete(obj)
            logger.warning(
                "{0} removed because of ascii error".format(
                    "/".join(obj.getPhysicalPath())))


# Old scale name to new scale name
IMAGE_SCALE_MAP = {
    'icon': 'icon',
    'large': 'large',
    'listing': 'listing',
    'mini': 'mini',
    'preview': 'preview',
    'thumb': 'thumb',
    'tile': 'tile',
    # BBB
    'article': 'preview',
    'artikel': 'preview',
    'carousel': 'preview',
    'company_index': 'thumb',
    'content': 'preview',
    'leadimage': 'tile',
    'portlet-fullpage': 'large',
    'portlet-halfpage': 'large',
    'portlet-links': 'thumb',
    'portlet': 'thumb',
    'staff_crop': 'thumb',
    'staff_index': 'thumb',
}


def image_scale_fixer(text):

    if text:
        for old, new in IMAGE_SCALE_MAP.items():
            # replace plone.app.imaging old scale names with new ones
            text = text.replace(
                '@@images/image/{0}'.format(old),
                '@@images/image/{0}'.format(new)
            )
            # replace AT traversing scales
            text = text.replace(
                'image_{0}'.format(old),
                '@@images/image/{0}'.format(new)
            )

    return text


def set_correctly_exclude_from_nav(pc):
    brains = [folder for folder in pc(
        review_state='published_and_hidden',
        portal_type='Folder') if not folder.exclude_from_nav]

    for brain in brains:
        obj = brain.getObject()
        obj.setExcludeFromNav(True)
        obj.reindexObject()
        logger.info('set exclude from nav for {}'.format(brain.getPath()))

    brains = [folder for folder in pc(
        review_state='published_and_shown',
        portal_type='Folder') if folder.exclude_from_nav]
    for brain in brains:
        obj = brain.getObject()
        obj.setExcludeFromNav(False)
        obj.reindexObject()
        logger.info('unset exclude from nav for {}'.format(brain.getPath()))


def fix_at_image_scales(context):
    catalog = api.portal.get_tool('portal_catalog')
    query = {}
    query['object_provides'] = 'plone.app.contenttypes.behaviors.richtext.IRichText'  # noqa
    results = catalog(**query)
    logger.info('There are {0} in total, stating migration...'.format(
        len(results)))
    for result in results:
        try:
            obj = result.getObject()
        except:
            logger.warning(
                'Not possible to fetch object from catalog result for '
                'item: {0}.'.format(result.getPath()))
            continue

        text = getattr(obj, 'text', None)
        if text:
            clean_text = image_scale_fixer(text.raw)
            if clean_text != text.raw:
                obj.text = RichTextValue(
                    raw=clean_text,
                    mimeType=text.mimeType,
                    outputMimeType=text.outputMimeType,
                    encoding=text.encoding
                )
                obj.reindexObject(idxs=('SearchableText', ))
                logger.info('Text cleanup for {0}'.format(
                    '/'.join(obj.getPhysicalPath())
                ))


def fix_portlets_image_scales(obj):
    # also take custom portlet managers into account
    # managers = [reg.name for reg in getSiteManager().registeredUtilities()
    #                  if reg.provided == IPortletManager]
    # faster, but no custom managers
    managers = [u'plone.leftcolumn', u'plone.rightcolumn']

    # copy information which categories are hidden for which manager
    blacklist_status = IAnnotations(obj).get(
        CONTEXT_BLACKLIST_STATUS_KEY, None)
    if blacklist_status is not None:
        IAnnotations(obj)[CONTEXT_BLACKLIST_STATUS_KEY] = deepcopy(
            blacklist_status)

    # copy all portlet assignments (visibilty is stored as annotation
    # on the assignments and gets copied here too)
    for manager in managers:
        column = getUtility(IPortletManager, manager)
        mappings = getMultiAdapter((obj, column), IPortletAssignmentMapping)
        for key, assignment in mappings.items():
            # skip possibly broken portlets here
            if not hasattr(assignment, '__Broken_state__'):
                if getattr(assignment, 'text', None):
                    clean_text = image_scale_fixer(assignment.text)
                    assignment.text = clean_text
            else:
                logger.warn(u'skipping broken portlet assignment {0} '
                            'for manager {1}'.format(key, manager))


def is_pam_installed_and_not_used(portal):
    installer = api.portal.get_tool('portal_quickinstaller')
    installed = False
    used = False
    if installer.isProductInstalled('plone.app.multilingual'):
        logger.info('PAM is installed')
        installed = True

    catalog = api.portal.get_tool('portal_catalog')
    brains = catalog(portal_type=('LRF', 'LIF'))
    if len(brains) != 0:
        logger.info('PAM is used')
        used = True

    if installed and not used:
        logger.info('PAM is installed and NOT used')
        return True
    else:
        return False


def enabled_behaviors(portal):
    types = {
        'Document': [
            'cpskin.core.behaviors.metadata.IStandardTags',
            'cpskin.core.behaviors.metadata.IHiddenTags',
            'cpskin.core.behaviors.metadata.IISearchTags',
            'cpskin.core.behaviors.metadata.IIAmTags',
            'collective.geo.behaviour.interfaces.ICoordinates'],
        'Event': [
            'cpskin.core.behaviors.metadata.IStandardTags',
            'cpskin.core.behaviors.metadata.IHiddenTags',
            'cpskin.core.behaviors.metadata.IISearchTags',
            'cpskin.core.behaviors.metadata.IIAmTags',
            'collective.geo.behaviour.interfaces.ICoordinates'],
        'Folder': [
            'cpskin.core.behaviors.metadata.IStandardTags',
            'cpskin.core.behaviors.metadata.IHiddenTags',
            'cpskin.core.behaviors.metadata.IISearchTags',
            'cpskin.core.behaviors.metadata.IIAmTags',
            'cpskin.core.behaviors.metadata.IUseKeywordHomepage',
            'eea.facetednavigation.subtypes.interfaces.IPossibleFacetedNavigable',
            'collective.plonetruegallery.interfaces.IGallery'],
        'News Item': [
            'cpskin.core.behaviors.metadata.IStandardTags',
            'cpskin.core.behaviors.metadata.IHiddenTags',
            'cpskin.core.behaviors.metadata.IISearchTags',
            'cpskin.core.behaviors.metadata.IIAmTags',
            'collective.geo.behaviour.interfaces.ICoordinates'],
        'Collection': [
            'cpskin.core.behaviors.metadata.IStandardTags',
            'cpskin.core.behaviors.metadata.IHiddenTags',
            'cpskin.core.behaviors.metadata.IISearchTags',
            'cpskin.core.behaviors.metadata.IIAmTags',
            'eea.facetednavigation.subtypes.interfaces.IPossibleFacetedNavigable',
            'collective.plonetruegallery.interfaces.IGallery',
        ]
    }
    for typename in types.keys():
        for behavior in types[typename]:
            add_behavior(typename, behavior)


def enabled_leadimage(portal):
    lead_iname = 'plone.app.contenttypes.behaviors.leadimage.ILeadImage'
    prefs = ILeadImagePrefsForm(portal)
    for typename in prefs.allowed_types:
        add_behavior(typename, lead_iname)
        logger.info("Enabled leadimage for {} content types".format(typename))


def add_behavior(type_name, behavior_name):
    fti = queryUtility(IDexterityFTI, name=type_name)
    behaviors = list(fti.behaviors)
    if behavior_name not in behaviors:
        behaviors.append(behavior_name)
        fti._updateProperty('behaviors', tuple(behaviors))


def remove_old_topics():
    catalog = api.portal.get_tool('portal_catalog')
    for brain in catalog(portal_type=('Topic',)):
        obj = brain.getObject()
        api.content.delete(obj)
        logger.warning(
            "{0} removed because it's a old Topic".format(
                "/".join(obj.getPhysicalPath())))


def remove_old_import_step(setup):
    # context is portal_setup which is nice
    registry = setup.getImportStepRegistry()
    old_step = u'plone.multilingualbehavior.uninstall'
    if old_step in registry.listSteps():
        registry.unregisterStep(old_step)

        # Unfortunately we manually have to signal the context
        # (portal_setup) that it has changed otherwise this change is
        # not persisted.
        setup._p_changed = True
        logger.info(
            "Old %s import step removed from import registry.", old_step)


def safe_tags(oldtag):
    return tuple(safe_utf8(tag) for tag in oldtag)


@implementer(ICustomMigrator)
@adapter(Interface)
class CpskinMigrator(object):

    def __init__(self, context):
        self.context = context

    def migrate(self, old, new):
        new_path = "/".join(new.getPhysicalPath())
        if ISyndicatable.providedBy(new):
            old_feed_settings = IFeedSettings(old)
            IFeedSettings(new).enabled = old_feed_settings.enabled
            logger.info(
                "{0} RSS enabled settings copied from old".format(new_path))

        # XXX Merge subject and standard tags
        if old.Subject():
            new.standardTags = safe_tags(old.Subject())
            logger.info(
                "{0} standardTags added from subjects".format(new_path))

        # standardTags
        if getattr(old, 'standardTags', None):
            new.standardTags = safe_tags(old.standardTags)
            # new.subjects = old.standardTags
            logger.info("{0} standardTags added".format(new_path))

        # hiddenTags
        if getattr(old, 'hiddenTags', None):
            new.hiddenTags = safe_tags(old.hiddenTags)
            logger.info("{0} hiddenTags added".format(new_path))

        # isearchTags
        if getattr(old, 'isearchTags', None):
            new.isearchTags = safe_tags(old.isearchTags)
            logger.info("{0} isearchTags added".format(new_path))

        # iamTags
        if getattr(old, 'iamTags', None):
            new.iamTags = safe_tags(old.iamTags)
            logger.info("{0} iamTags added".format(new_path))

        interfaces = [
            IAlbumCollection,
            IBannerActivated,
            IFolderViewSelectedContent,
            IFolderViewWithBigImages,
            ILocalBannerActivated,
            IMediaActivated,
            IVideoCollection,
            IViewletMenuToolsBox,
            IViewletMenuToolsFaceted,
            IFourthLevelNavigation,
            IDirectAccess,
            IFacetedNavigable,
            IDisableSmartFacets,
            IHidePloneLeftColumn,
            IHidePloneRightColumn,
            ICriteria,
            ILanguageWidgetAdapter,
            IFacetedWrapper,
            IViewsInfo,
            IAlphabeticWidget,
            ICriterion,
            IWidget,
            IWidgetsInfo,
            IResultsFilterWidget,
        ]
        for interface in interfaces:
            if interface.providedBy(old):
                alsoProvides(new, interface)
                logger.info("{0} provides {1}".format(
                    new_path, str(interface)))

        # XXX choose between old and new
        fix_portlets_image_scales(old)
        fix_portlets_image_scales(new)

        # minisites

        # large plone folder

        # fix event timezone
        if IDXEvent.providedBy(new):
            new.timezone = timezone

        # migrate faceted criteria
        if IFacetedNavigable.providedBy(old):
            criteria = Criteria(new)
            criteria._update(ICriteria(old).criteria)
            logger.info("Add facteted criteria for {0}".format(new_path))

        # migrate geolocalisation
        if IGeoreferenceable.providedBy(old):
            try:
                IWriteGeoreferenced(old)
                old_coord = Coordinates(old).coordinates
                new_coord = Coordinates(new)
                new_coord.coordinates = old_coord
                logger.info("Add coord criteria for {0}".format(new_path))
            except:
                pass

        # migrate sticky
        if getattr(old, 'sticky', None):
            # TODO delete old portal_atct
            add_behavior(new.portal_type, 'collective.sticky.behavior.ISticky')
            new.sticky = old.sticky
            logger.info("{0} sticky added".format(new_path))

        # # Rescales images
        # if ILeadImage.providedBy(new):
        #     field = old.getField('leadImage')
        #     if field is not None:
        #         field.removeScales(old)
        #         field.createScales(old)
        # if new.portal_type == "Image":
        #     field = old.getField('image')
        #     if field is not None:
        #         field.removeScales(old)
        #         field.createScales(old)
