# -*- coding: utf-8 -*-
from plone import api
from Products.CMFCore.utils import getToolByName
from plone.app.workflow.remap import remap_workflow
from cpskin.migration.upgradesteps import cleanupRegistry
from plone.browserlayer.utils import unregister_layer
import logging
logger = logging.getLogger('cpskin.migration')


def deleteCPSkin3Workflows(portal):
    wt = getToolByName(portal, 'portal_workflow')
    if wt.get('cpskin3_moderation_workflow'):
        wt.manage_delObjects(['cpskin3_moderation_workflow', 'cpskin3_workflow'])
    if 'readonly_workflow' in wt.objectIds():
        wt.manage_delObjects(['readonly_workflow'])


def getNewDefaultChain(portal):
    wt = getToolByName(portal, 'portal_workflow')
    default = wt.getDefaultChain()
    newWf = default[0]
    if default[0] == 'cpskin3_workflow':
        newWf = 'cpskin_workflow'
    elif default[0] == 'cpskin3_moderation_workflow':
        newWf = 'cpskin_moderation_workflow'
    return newWf


def migrateAfterCpSkinInstall(context):
    if context.readDataFile('cpskin_migration_after.txt') is None:
        return
    portal = context.getSite()
    defaultChain = getNewDefaultChain(portal)
    setup_tool = getToolByName(portal, 'portal_setup')
    if api.group.get(groupname='citizens'):
        setup_tool.runAllImportStepsFromProfile('profile-cpskin.policy:members-configuration')
    else:
        setup_tool.runAllImportStepsFromProfile('profile-cpskin.policy:default')

    wt = getToolByName(portal, 'portal_workflow')
    tt = getToolByName(portal, 'portal_types')

    nondefault = [info[0] for info in wt.listChainOverrides()]
    type_ids = [type for type in tt.listContentTypes() if type not in nondefault]
    wt.setChainForPortalTypes(type_ids, wt.getDefaultChain())
    wt.setDefaultChain(defaultChain)
    chain = '(Default)'
    state_map = {'published_and_shown': 'published_and_shown',
                 'created': 'created',
                 'published_and_hidden': 'published_and_hidden'}

    remap_workflow(portal, type_ids=type_ids, chain=chain,
                   state_map=state_map)

    deleteCPSkin3Workflows(portal)

    portal_migration = getToolByName(portal, 'portal_migration')
    portal_migration.upgrade()
    uninstall_products(portal)
    delete_old_skins(portal)
    clean_up_zmi(portal)
    cleanupRegistry(setup_tool)
    logger.info('old registry deleted.')


def delete_old_skins(portal):
    skins = [
        'iconified_document_actions_styles',
        'iconifieddocumentactions_styles',
        'kss',
        'plone_kss',
        'TTGoogleMapCss',
        'TTGoogleMapImages',
        'TTGoogleMapJS',
        'TTGoogleMapScripts',
        'TTGoogleMapViews',
        'contacts',
        'archetypes_kss',
    ]

    themes = ['Plone Classic Theme', 'Plone Default', 'Sunburst Theme']
    # XXX delete unexistant folder skins for properties skins (portal_skins -> properties)

    for skin in skins:
        if hasattr(portal.portal_skins, skin):
            portal.portal_skins.manage_delObjects(ids=[skin, ])
            logger.info('Deleted: {} skin'.format(skin))
    # remove old registered CSS, does not fail if resource not exists
    portal.portal_css.unregisterResource('iconifieddocumentactions.css')
    # unregister old BrowserLayer 'communesplone.iconified_document_actions.layer'
    try:
        unregister_layer('communesplone.iconified_document_actions.layer')
    except KeyError:
    # layer was already unregistered, we pass...
        pass


def clean_up_zmi(portal):
    old_zmi_objects = ['portal_cpskin', 'portal_kss']
    for old_zmi_object in old_zmi_objects:
        if hasattr(portal, old_zmi_object):
            portal.manage_delObjects(ids=[old_zmi_object, ])
            logger.info('Deleted: {}'.format(old_zmi_object))


def uninstall_products(portal):
    #import ipdb; ipdb.set_trace()
    installer = getToolByName(portal, 'portal_quickinstaller')
    products = [
        #'webcouturier.dropdownmenu',
        'plone.app.kss',
        'communesplone.iconified_document_actions',
        'directory',
        'tecnoteca.googlemap',
        #'acptheme.cpskin3'
    ]
    for prodcut in products:
        if installer.isProductInstalled(prodcut):
            installer.uninstallProducts([prodcut])
