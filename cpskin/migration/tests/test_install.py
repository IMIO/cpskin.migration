# -*- coding: utf-8 -*-
import unittest2 as unittest
from Products.CMFCore.utils import getToolByName
from cpskin.migration.testing import (CPSKIN_MIGRATION_INTEGRATION_TESTING,
                                      CPSKIN_MIGRATION_WITH_MEMBERS_INTEGRATION_TESTING)


class TestInstallWithMembers(unittest.TestCase):
    layer = CPSKIN_MIGRATION_WITH_MEMBERS_INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer['portal']

    def test_workflows_with_members(self):
        pw = getToolByName(self.portal, 'portal_workflow')
        self.assertEqual(pw.objectIds(), ['folder_workflow',
                                          'intranet_folder_workflow',
                                          'intranet_workflow',
                                          'one_state_workflow',
                                          'plone_workflow',
                                          'simple_publication_workflow',
                                          'comment_review_workflow',
                                          'cpskin_workflow',
                                          'cpskin_moderation_workflow',
                                          'cpskin_readonly_workflow'])


class TestInstall(unittest.TestCase):
    layer = CPSKIN_MIGRATION_INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer['portal']

    def test_topic_is_not_installable(self):
        types_tool = getToolByName(self.portal, 'portal_types')
        fti = types_tool.getTypeInfo('Topic')
        self.assertFalse(fti.global_allow)

    def test_topic_ids(self):
        self.assertTrue('actualites' in self.portal.objectIds())
        self.assertTrue('evenements' in self.portal.objectIds())

    def test_workflows(self):
        pw = getToolByName(self.portal, 'portal_workflow')
        self.assertEqual(pw.objectIds(), ['folder_workflow',
                                          'intranet_folder_workflow',
                                          'intranet_workflow',
                                          'one_state_workflow',
                                          'plone_workflow',
                                          'simple_publication_workflow',
                                          'comment_review_workflow',
                                          'cpskin_workflow',
                                          'cpskin_moderation_workflow'])
