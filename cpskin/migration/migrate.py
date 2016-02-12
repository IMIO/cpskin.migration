# -*- coding: utf-8 -*-
from copy import deepcopy
from cpskin.core.interfaces import IAlbumCollection
from cpskin.core.interfaces import IBannerActivated
from cpskin.core.interfaces import IFolderViewSelectedContent
from cpskin.core.interfaces import IFolderViewWithBigImages
from cpskin.core.interfaces import ILocalBannerActivated
from cpskin.core.interfaces import IMediaActivated
from cpskin.core.interfaces import IVideoCollection
from cpskin.core.viewlets.interfaces import IViewletMenuToolsBox
from cpskin.core.viewlets.interfaces import IViewletMenuToolsFaceted
from cpskin.menu.interfaces import IFourthLevelNavigation

from eea.facetednavigation.criteria.handler import Criteria
from eea.facetednavigation.criteria.interfaces import ICriteria
from eea.facetednavigation.indexes.language.interfaces import ILanguageWidgetAdapter
from eea.facetednavigation.interfaces import IFacetedNavigable
from eea.facetednavigation.settings.interfaces import IDisableSmartFacets
from eea.facetednavigation.settings.interfaces import IHidePloneLeftColumn
from eea.facetednavigation.settings.interfaces import IHidePloneRightColumn
from eea.facetednavigation.subtypes.interfaces import IFacetedNavigable
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
        ps.runAllImportStepsFromProfile('profile-plone.app.multilingual:uninstall')
        noLongerProvides(request, IPloneAppMultilingualInstalled)
    pc = api.portal.get_tool(name='portal_catalog')
    ps = api.portal.get_tool(name='portal_setup')
    # clean up old plone.multilingualbehaviors
    remove_old_import_step(ps)
    # Fix bug, sometimes obj with publish_and_hidden are still in navigation
    set_correctly_exclude_from_nav(pc)

    logger.info('Starting rebuilding catalog')
    pc.clearFindAndRebuild()

    logger.info('Upgrate to dx')
    logger.info("Installing plone.app.contenttypes")
    ps.runAllImportStepsFromProfile('profile-plone.app.contenttypes:default')
    alsoProvides(request, IPloneAppContenttypesLayer)

    # set view for dexteity content types
    ps.runImportStepFromProfile('profile-cpskin.migration:migratetodx', 'typeinfo')

    logger.info("Enabled cpskin behavior for dx content types")
    enabled_behaviors(portal)

    reg = getUtility(IRegistry)
    settings = reg.forInterface(IEventSettings, prefix="plone.app.event")
    if not settings.portal_timezone:
        logger.info('Set timezone to Europe/Brussels')
        settings.portal_timezone = timezone

    migration_view = getMultiAdapter((portal, request), name=u'migrate_from_atct')
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
    # results = migration_view(from_form=True)
    idp = pc(path={'query': '/couvin/actualites/actualites'}, is_default_page=1)
    logger.info('---------------- {}'.format(len(idp)))
    logger.info(results)

    logger.info('Fix image scales')
    fix_at_image_scales(portal)
    fix_portlets_image_scales(portal)


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
    blacklist_status = IAnnotations(obj).get(CONTEXT_BLACKLIST_STATUS_KEY, None)
    if blacklist_status is not None:
        IAnnotations(obj)[CONTEXT_BLACKLIST_STATUS_KEY] = deepcopy(blacklist_status)

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
            'cpskin.core.behaviors.metadata.IHiddenTags',
            'cpskin.core.behaviors.metadata.IISearchTags',
            'cpskin.core.behaviors.metadata.IIAmTags',
            'plone.app.contenttypes.behaviors.leadimage.ILeadImage',
            'collective.geo.behaviour.interfaces.ICoordinates'],
        'Event': [
            'cpskin.core.behaviors.metadata.IHiddenTags',
            'cpskin.core.behaviors.metadata.IISearchTags',
            'cpskin.core.behaviors.metadata.IIAmTags',
            'plone.app.contenttypes.behaviors.leadimage.ILeadImage',
            'collective.geo.behaviour.interfaces.ICoordinates'],
        'Folder': [
            'cpskin.core.behaviors.metadata.IHiddenTags',
            'cpskin.core.behaviors.metadata.IISearchTags',
            'cpskin.core.behaviors.metadata.IIAmTags',
            'plone.app.contenttypes.behaviors.leadimage.ILeadImage',
            'eea.facetednavigation.subtypes.interfaces.IPossibleFacetedNavigable',
            'collective.plonetruegallery.interfaces.IGallery'],
        'News Item': [
            'cpskin.core.behaviors.metadata.IHiddenTags',
            'cpskin.core.behaviors.metadata.IISearchTags',
            'cpskin.core.behaviors.metadata.IIAmTags',
            'collective.geo.behaviour.interfaces.ICoordinates'],
        'Collection': [
            'eea.facetednavigation.subtypes.interfaces.IPossibleFacetedNavigable',
            'collective.plonetruegallery.interfaces.IGallery',
        ]
    }
    for typename in types.keys():
        for behavior in types[typename]:
            fti = queryUtility(IDexterityFTI, name=typename)
            behaviors = list(fti.behaviors)
            behaviors.append(behavior)
            fti._updateProperty('behaviors', tuple(behaviors))


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
        logger.info("Old %s import step removed from import registry.", old_step)


@implementer(ICustomMigrator)
@adapter(Interface)
class CpskinMigrator(object):

    def __init__(self, context):
        self.context = context

    def migrate(self, old, new):
        new_path = "/".join(new.getPhysicalPath())

        # standardTags
        if getattr(old, 'standardTags', None):
            new.subject = old.standardTags
            logger.info("{0} standardTags added".format(new_path))

        # hiddenTags
        if getattr(old, 'hiddenTags', None):
            new.hiddenTags = old.hiddenTags
            logger.info("{0} hiddenTags added".format(new_path))

        # isearchTags
        if getattr(old, 'isearchTags', None):
            new.isearchTags = old.isearchTags
            logger.info("{0} isearchTags added".format(new_path))

        # iamTags
        if getattr(old, 'iamTags', None):
            new.iamTags = old.iamTags
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
                logger.info("{0} provides {1}".format(new_path, str(interface)))

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

        # migrate geolocalisation
