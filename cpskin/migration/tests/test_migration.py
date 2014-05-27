# -*- coding: utf-8 -*-
import os
import os.path
import unittest2 as unittest
from zope.component import getUtilitiesFor
from plone.app.testing import applyProfile
from cpskin.minisite.interfaces import IMinisite
from cpskin.migration.testing import CPSKIN_MIGRATION_BASIC_INTEGRATION_TESTING


class TestInstallWithMembers(unittest.TestCase):
    layer = CPSKIN_MIGRATION_BASIC_INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer['portal']

    def _install_cpskin3(self):
        applyProfile(self.portal, 'Products.CMFPlone:plone')
        applyProfile(self.portal, 'Products.CMFPlone:plone-content')
        applyProfile(self.portal, 'acptheme.cpskin3:default')
        applyProfile(self.portal, 'acptheme.cpskin3:extra')
        applyProfile(self.portal, 'acptheme.cpskin3:members-configuration')

    def _run_migration(self):
        applyProfile(self.portal, 'cpskin.migration:default')

    def test_minisite_migration(self):
        self._install_cpskin3()
        self.portal.portal_cpskin.miniSitesDict['http://sub.domain.be'] = ('http://nohost/plone/news', '/plone/news')
        self._run_migration()
        minisite_directory = os.path.join(os.environ['CLIENT_HOME'],
                                          'minisites')
        self.assertTrue(os.path.exists(minisite_directory))
        config_file = os.path.join(minisite_directory, 'minisite.cfg')
        self.assertTrue(os.path.exists(config_file))
        with open(config_file, 'r') as configfile:
            self.assertEqual(configfile.read(), '[http://sub.domain.be]\nminisite_url = http://nohost/plone/news\nsearch_path = /plone/news\n\n')
        minisites = list(getUtilitiesFor(IMinisite))
        self.assertEqual(len(minisites), 1)
        minisitePath, minisite = minisites[0]
        self.assertEqual(minisitePath, u'/plone/news')
        self.assertEqual(minisite.main_portal_url, u'http://sub.domain.be')
        self.assertEqual(minisite.minisite_url, 'http://nohost/plone/news')
        self.assertEqual(minisite.search_path, '/plone/news')
