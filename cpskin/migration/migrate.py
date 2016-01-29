# -*- coding: utf-8 -*-
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
from plone import api
from plone.app.contenttypes.migration.migration import ICustomMigrator
from zope.component import adapter
from zope.component import getMultiAdapter
from zope.interface import alsoProvides
from zope.interface import Interface
from zope.interface import implementer

import logging

logger = logging.getLogger('cpskin.migration.migrate')


def migratetodx(setup):
    if setup.readDataFile('cpskin.migration-migratetodx.txt') is None:
        return

    logger.info('Upgrate to dx')
    portal = setup.getSite()
    request = getattr(portal, 'REQUEST', None)
    # pc = api.portal.get_tool(name='portal_catalog')
    # pc.clearFindAndRebuild()
    # ps = api.portal.get_tool(name='portal_setup')
    # ps.runAllImportStepsFromProfile('profile-plone.app.contenttypes:default')
    # plone.app.contenttypes is installed by generic setup (metadata.xml)
    from plone.app.contenttypes.interfaces import IPloneAppContenttypesLayer
    alsoProvides(request, IPloneAppContenttypesLayer)

    migration_view = getMultiAdapter((portal, request), name=u'migrate_from_atct')
    content_types = [
        'News Item',
        'BlobFile',
        'BlobImage',
        'Collection',
        'Document',
        'Folder',
        'Link',
        'Topic',
        'Event'
    ]
    # call the migration-view above to actually migrate stuff.
    results = migration_view(
        content_types=content_types,
        migrate_schemaextended_content=True,
        migrate_references=True,
        from_form=True,
    )
    logger.info(results)
    # sdm = getToolByName(portal, "session_data_manager")
    # session = sdm.getSessionData(create=True)
    # session.set("atct_migrator_results", results)
    # url = portal.absolute_url()
    # request.response.redirect(url + "/@@atct_migrator_results")


@implementer(ICustomMigrator)
@adapter(Interface)
class CpskinMigrator(object):

    def __init__(self, context):
        self.context = context

    def migrate(self, old, new):
        new_path = "/".join(new.getPhysicalPath())

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
        ]
        for interface in interfaces:
            if interface.providedBy(old):
                alsoProvides(new, interface)
                logger.info("{0} provides {1}".format(new_path, str(interface)))

        # view folder in homepage


        # default view
        # if old.getDefaultPage():
        #     new.setDefaultPage(old.getDefaultPage())
        #     logger.info("{0} set a default page".format(new_path))

        # minisites

        # media viewlet

        # 4levelnavigation
