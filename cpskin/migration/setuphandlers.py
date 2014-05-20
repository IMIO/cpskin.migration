# -*- coding: utf-8 -*-
import os
from plone import api
from Products.CMFCore.utils import getToolByName


def migrateTopics(portal):
    # XXX todo
    pc = getToolByName(portal, 'portal_catalog')
    for brainTopic in pc(portal_type='Topic'):
        topic = brainTopic.getObject()
        api.content.delete(obj=topic)


def migrateTopicIds(portal):
    pc = getToolByName(portal, 'portal_catalog')
    for brainTopic in pc(portal_type='Topic'):
        if brainTopic.getId == 'aggregator':
            topic = brainTopic.getObject()
            topic_parent = topic.aq_parent
            api.content.rename(obj=topic, new_id='index')
            if topic_parent.getId() == 'news':
                api.content.rename(obj=topic_parent, new_id='actualites')
            if topic_parent.getId() == 'events':
                api.content.rename(obj=topic_parent, new_id='evenements')


def migrateBeforeCpSkinInstall(context):
    if context.readDataFile('cpskin_migration_before.txt') is None:
        return
    portal = context.getSite()
    if os.environ.get('ZOPETESTCASE'):
        # required for testing - topic object need a _p_jar for rename
        import transaction
        transaction.savepoint()
    migrateTopicIds(portal)
    migrateTopics(portal)


def deleteCPSkin3Workflows(portal):
    wt = getToolByName(portal, 'portal_workflow')
    wt.manage_delObjects(['cpskin3_moderation_workflow', 'cpskin3_workflow'])
    if 'readonly_workflow' in wt.objectIds():
        wt.manage_delObjects(['readonly_workflow'])


def migrateAfterCpSkinInstall(context):
    if context.readDataFile('cpskin_migration_after.txt') is None:
        return
    portal = context.getSite()
    setup_tool = getToolByName(portal, 'portal_setup')
    if api.group.get(groupname='citizens'):
        setup_tool.runAllImportStepsFromProfile('profile-cpskin.policy:members-configuration')
    else:
        setup_tool.runAllImportStepsFromProfile('profile-cpskin.policy:default')
    deleteCPSkin3Workflows(portal)
