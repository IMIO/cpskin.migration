# -*- coding: utf-8 -*-

import os
from plone import api
from Products.ATContentTypes.lib import constraintypes
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import _createObjectByType


def publishContent(wftool, content):
    if wftool.getInfoFor(content, 'review_state') != 'published':
        actions = [a.get('id') for a in wftool.listActions(object=content)]
        # we need to handle both workflows
        if 'publish_and_hide' in actions:
            wftool.doActionFor(content, 'publish_and_hide')
        elif 'publish' in actions:
            wftool.doActionFor(content, 'publish')


def createEventsAndNews(portal):
    """
    Inspired by Products.CMFPlone.setuphandlers
    """
    existing = portal.keys()
    language = portal.Language()
    wftool = getToolByName(portal, "portal_workflow")

    # News topic
    if 'actualites' not in existing:
        news_title = u'Actualités'
        news_desc = 'Actualités du site'
        _createObjectByType('Folder', portal, id='actualites',
                            title=news_title, description=news_desc)
        _createObjectByType('Collection', portal.actualites, id='index',
                            title=news_title, description=news_desc)

        folder = portal.actualites
        folder.setConstrainTypesMode(constraintypes.ENABLED)
        folder.setLocallyAllowedTypes(['News Item'])
        folder.setImmediatelyAddableTypes(['News Item'])
        folder.setDefaultPage('index')
        folder.unmarkCreationFlag()
        folder.setLanguage(language)
        publishContent(wftool, folder)

        topic = portal.actualites.index
        topic.setLanguage(language)

        query = [{'i': 'portal_type',
                  'o': 'plone.app.querystring.operation.selection.is',
                  'v': ['News Item']},
                 {'i': 'review_state',
                  'o': 'plone.app.querystring.operation.selection.is',
                  'v': ['published']}]
        topic.setQuery(query)

        topic.setSort_on('effective')
        topic.setSort_reversed(True)
        topic.setLayout('folder_summary_view')
        topic.unmarkCreationFlag()
        publishContent(wftool, topic)

    # Events topic
    if 'evenements' not in existing:
        events_title = 'Événements'
        events_desc = 'Événements du site'
        _createObjectByType('Folder', portal, id='evenements',
                            title=events_title, description=events_desc)
        _createObjectByType('Collection', portal.evenements, id='index',
                            title=events_title, description=events_desc)

        folder = portal.evenements
        folder.setConstrainTypesMode(constraintypes.ENABLED)
        folder.setLocallyAllowedTypes(['Event'])
        folder.setImmediatelyAddableTypes(['Event'])
        folder.setDefaultPage('index')
        folder.unmarkCreationFlag()
        folder.setLanguage(language)
        publishContent(wftool, folder)

        topic = folder.index
        topic.unmarkCreationFlag()
        topic.setLanguage(language)

        query = [{'i': 'portal_type',
                  'o': 'plone.app.querystring.operation.selection.is',
                  'v': ['Event']},
                 {'i': 'start',
                  'o': 'plone.app.querystring.operation.date.afterToday',
                  'v': ''},
                 {'i': 'review_state',
                  'o': 'plone.app.querystring.operation.selection.is',
                  'v': ['published']}]
        topic.setQuery(query)
        topic.setSort_on('start')
        publishContent(wftool, topic)


def migrateTopics(portal):
    """
    We migrate only main news and events to collections
    LATER: maybe migrate all the Topics of the site
    """
    if portal.hasObject('actualites'):
        api.content.delete(obj=portal['actualites'])
    if portal.hasObject('news'):
        api.content.delete(obj=portal['news'])
    if portal.hasObject('evenements'):
        api.content.delete(obj=portal['evenements'])
    if portal.hasObject('events'):
        api.content.delete(obj=portal['events'])
    createEventsAndNews(portal)


def migrateTopicIds(portal):
    pc = getToolByName(portal, 'portal_catalog')
    for brainTopic in pc(portal_type='Topic'):
        topic = brainTopic.getObject()
        topic_parent = topic.aq_parent
        if brainTopic.getId == 'aggregator':
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
    if portal.hasObject('Members'):
        # required to be able to create help-page
        portal['Members'].setConstrainTypesMode(0)


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
