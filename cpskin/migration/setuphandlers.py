# -*- coding: utf-8 -*-
from plone import api
from Products.CMFCore.utils import getToolByName
from Products.GenericSetup.interfaces import IUpgradeSteps
from zope.component import getGlobalSiteManager
from plone.app.upgrade.utils import unregisterSteps
from plone.app.upgrade.v40.alphas import cleanUpToolRegistry
from plone.app.workflow.remap import remap_workflow
from cpskin.migration.upgradesteps import cleanupRegistry
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
    logger.info('old registry deleted.')

    portal_migration = getToolByName(portal, 'portal_migration')
    portal_migration.upgrade()
    migrate_directory(portal)
    delete_iconified_document_actions(portal)
    delete_technoteca_googlemap(portal)
    remove_kss(portal)
    cleanupRegistry(setup_tool)

    # delete registred upgrade steps
    sm = getGlobalSiteManager()
    sm.unregisterUtility(provided=IUpgradeSteps, name=u'acptheme.cpskin3:default')
    delete_old_skin_folder(portal, 'contacts')
    clean_up_zmi(portal)


def migrate_directory(portal):
    setup_tool = getToolByName(portal, 'portal_setup')
    logger.info("Starting migration of Directory")
    setup_tool.runAllImportStepsFromProfile('profile-collective.directory:migration')
    setup_tool.runAllImportStepsFromProfile('profile-Products.directory:uninstall')

    # delete registred upgrade steps
    sm = getGlobalSiteManager()
    sm.unregisterUtility(provided=IUpgradeSteps, name=u'Products.directory:default')

    logger.info("Migration of Directory ran")


def delete_iconified_document_actions(portal):
    setup_tool = getToolByName(portal, 'portal_setup')
    uninstall_product(portal, 'communesplone.iconified_document_actions')
    setup_tool.runAllImportStepsFromProfile('profile-communesplone.iconified_document_actions:uninstall')
    logger.info("communesplone.iconified_document_actions deleted")


def delete_technoteca_googlemap(portal):
    setup_tool = getToolByName(portal, 'portal_setup')
    uninstall_product(portal, 'tecnoteca.googlemap')
    setup_tool.runAllImportStepsFromProfile('profile-tecnoteca.googlemap:uninstall')
     # delete registred upgrade steps
    sm = getGlobalSiteManager()
    sm.unregisterUtility(provided=IUpgradeSteps, name=u'tecnoteca.googlemap:default')


def clean_up_zmi(portal):
    old_zmi_objects = ['portal_cpskin']
    for old_zmi_object in old_zmi_objects:
        if hasattr(portal, old_zmi_object):
            portal.manage_delObjects(ids=[old_zmi_object, ])
            logger.info('Deleted: {}'.format(old_zmi_object))


def uninstall_product(portal, product_name):
    installer = getToolByName(portal, 'portal_quickinstaller')
    if installer.isProductInstalled(product_name):
        installer.uninstallProducts([product_name])


def delete_old_skin_folder(portal, folder_name):
    skinstool = getToolByName(portal, 'portal_skins')
    selections = skinstool._getSelections()
    for skin_name in selections.keys():
        layers = selections[skin_name].split(',')
        if folder_name in layers:
            layers.remove(folder_name)
        skinstool.addSkinSelection(skin_name, ','.join(layers))
    if hasattr(skinstool, folder_name):
        skinstool.manage_delObjects(ids=[folder_name, ])
    logger.info('Deleted: {} from portal_skins folder'.format(folder_name))


def remove_kss(portal):
    # remove KSS-related skin layers from all skins
    delete_old_skin_folder(portal, 'plone_kss')
    delete_old_skin_folder(portal, 'archetypes_kss')
    delete_old_skin_folder(portal, 'kss')

    # remove portal_kss tool
    portal = getToolByName(portal, 'portal_url').getPortalObject()
    if 'portal_kss' in portal:
        portal.manage_delObjects(['portal_kss'])

    # make sure portal_kss is no longer listed as a required tool
    setup_tool = getToolByName(portal, 'portal_setup')
    cleanUpToolRegistry(setup_tool)

    # make sure plone.app.kss is not activated in the quick installer
    uninstall_product(portal, 'plone.app.kss')

    unregisterSteps(setup_tool, import_steps=['kss_mimetype'])
