# -*- coding: utf-8 -*-
import ConfigParser
import os
from zope.component import adapter
from zope.component import getUtility, getMultiAdapter
from plone import api
from plone.portlets.interfaces import IPortletManager
from plone.portlets.interfaces import IPortletAssignmentMapping
from Products.directory.browser.interfaces import IDirectorySearchPortlet
from Products.directory.upgrades import common
from Products.CMFCore.utils import getToolByName
from Products.GenericSetup.interfaces import IBeforeProfileImportEvent
from acptheme.cpskin3.browser.cpskin3nav import ICPSkin3NavigationPortlet
from acptheme.cpskin3.upgradesteps import (correct_objects_id,
                                           cleanup_after_migrate)
from cpskin.minisite.startup import registerMinisites
from cpskin.core.browser.folderview import configure_folderviews


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
    configure_folderviews(portal)


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


def runAcpthemeUpgradeSteps(context):
    cleanup_after_migrate(context)
    correct_objects_id(context)


def runProductsDirectoryUpgradeStep(context):
    common(context)


@adapter(IBeforeProfileImportEvent)
def migrateBeforeCpSkin3Uninstall(event):
    profile_id = getProfileIdFromEvent(event)
    if profile_id == 'acptheme.cpskin3:uninstall':
        context = event.tool
        migrateMiniSite(context)
        runAcpthemeUpgradeSteps(context)


@adapter(IBeforeProfileImportEvent)
def migrateBeforeCpSkinInstall(event):
    profile_id = getProfileIdFromEvent(event)
    if profile_id == 'cpskin.migration:default':
        context = event.tool
        portal = api.portal.get()
        migrateTopics(portal)
        deleteOldPortlets(portal)
        runProductsDirectoryUpgradeStep(context)
        if portal.hasObject('Members'):
            # required to be able to create help-page
            portal['Members'].setConstrainTypesMode(0)
