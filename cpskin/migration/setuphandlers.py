# -*- coding: utf-8 -*-
from plone import api
from Products.CMFCore.utils import getToolByName


def deleteCPSkin3Workflows(portal):
    wt = getToolByName(portal, 'portal_workflow')
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
    deleteCPSkin3Workflows(portal)
    wt = getToolByName(portal, 'portal_workflow')
    wt.setDefaultChain(defaultChain)
