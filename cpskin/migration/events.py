# -*- coding: utf-8 -*-
import ConfigParser
import os
from zope.component import adapter
from zope.component import getUtility, getMultiAdapter
from plone import api
from plone.portlets.interfaces import IPortletManager
from plone.portlets.interfaces import IPortletAssignmentMapping
from Products.directory.browser.interfaces import IDirectorySearchPortlet
from Products.CMFCore.utils import getToolByName
from Products.GenericSetup.interfaces import IBeforeProfileImportEvent
from Products.CMFPlone.utils import _createObjectByType
from Products.ATContentTypes.lib import constraintypes
from acptheme.cpskin3.browser.cpskin3nav import ICPSkin3NavigationPortlet
from cpskin.minisite.startup import registerMinisites
from .utils import publishContent


def migrateMiniSite(context):
    CLIENT_HOME = os.environ["CLIENT_HOME"]
    cpskintool = getToolByName(context, 'portal_cpskin')
    minisites_directory = os.path.join(CLIENT_HOME, 'minisites')
    if not os.path.exists(minisites_directory):
        os.makedirs(minisites_directory)
    config = ConfigParser.RawConfigParser()
    for subdomain, listWithRealPath in cpskintool.getMiniSitesDict():
        config.add_section(subdomain)
        config.set(subdomain, 'minisite_url', listWithRealPath[0])
        config.set(subdomain, 'search_path', listWithRealPath[1])
    if config.sections():
        minisiteConfigFile = os.path.join(minisites_directory, 'minisite.cfg')
        with open(minisiteConfigFile, 'wb') as configfile:
            config.write(configfile)
        registerMinisites(object())


def createCollections(portal):
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

    # A la une topic
    if 'a-la-une' not in existing:
        une_title = 'A la une'
        une_desc = ''
        _createObjectByType('Folder', portal, id='a-la-une',
                            title=une_title, description=une_desc)
        _createObjectByType('Collection', portal.get('a-la-une'), id='index',
                            title=une_title, description=une_desc)

        folder = portal.get('a-la-une')
        folder.setConstrainTypesMode(constraintypes.ENABLED)
        folder.setDefaultPage('index')
        folder.unmarkCreationFlag()
        folder.setLanguage(language)
        publishContent(wftool, folder)

        topic = folder.index
        topic.unmarkCreationFlag()
        topic.setLanguage(language)

        query = [{'i': 'hiddenTags',
                  'o': 'plone.app.querystring.operation.selection.is',
                  'v': ['a la une']},
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
        unlock(portal['actualites'])
        api.content.delete(obj=portal['actualites'])
    if portal.hasObject('news'):
        unlock(portal['news'])
        api.content.delete(obj=portal['news'])
    if portal.hasObject('evenements'):
        unlock(portal['evenements'])
        api.content.delete(obj=portal['evenements'])
    if portal.hasObject('events'):
        unlock(portal['events'])
        api.content.delete(obj=portal['events'])
    if portal.hasObject('a-la-une'):
        unlock(portal['a-la-une'])
        api.content.delete(obj=portal['a-la-une'])
    createCollections(portal)


def unlock(obj):
    if obj.wl_isLocked():
        obj.wl_clearLocks()


def getProfileIdFromEvent(event):
    profile_id = event.profile_id
    if profile_id is None or not event.full_import:
        return

    if profile_id.startswith("profile-"):
        profile_id = profile_id[8:]
    return profile_id


def deleteOldPortlets(portal):
    for column in ["plone.leftcolumn", "plone.rightcolumn"]:
        manager = getUtility(IPortletManager, name=column)
        assignments = getMultiAdapter((portal, manager), IPortletAssignmentMapping)
    for portlet in assignments:
        if ICPSkin3NavigationPortlet.providedBy(assignments[portlet]) or IDirectorySearchPortlet.providedBy(assignments[portlet]):
            del assignments[portlet]


@adapter(IBeforeProfileImportEvent)
def migrateBeforeCpSkin3Uninstall(event):
    profile_id = getProfileIdFromEvent(event)
    if profile_id == 'acptheme.cpskin3:uninstall':
        context = event.tool
        migrateMiniSite(context)


@adapter(IBeforeProfileImportEvent)
def migrateBeforeCpSkinInstall(event):
    profile_id = getProfileIdFromEvent(event)
    if profile_id == 'cpskin.migration:default':
        portal = api.portal.get()
        migrateTopics(portal)
        deleteOldPortlets(portal)
        if portal.hasObject('Members'):
            # required to be able to create help-page
            portal['Members'].setConstrainTypesMode(0)
