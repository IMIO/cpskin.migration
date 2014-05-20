# -*- coding: utf-8 -*-
from plone.app.testing import PloneWithPackageLayer
from plone.app.testing import IntegrationTesting, FunctionalTesting
import cpskin.migration


CPSKIN_MIGRATION_FIXTURE = PloneWithPackageLayer(
    name="CPSKIN_MIGRATION_FIXTURE",
    zcml_filename="testing.zcml",
    zcml_package=cpskin.migration,
    gs_profile_id="cpskin.migration:testing")

CPSKIN_WITH_MEMBERS_MIGRATION_FIXTURE = PloneWithPackageLayer(
    name="CPSKIN_WITH_MEMBERS_MIGRATION_FIXTURE",
    zcml_filename="testing.zcml",
    zcml_package=cpskin.migration,
    gs_profile_id="cpskin.migration:testingwithmembers")


CPSKIN_MIGRATION_INTEGRATION_TESTING = IntegrationTesting(
    bases=(CPSKIN_MIGRATION_FIXTURE, ),
    name="CPSKIN_MIGRATION_INTEGRATION_TESTING")

CPSKIN_MIGRATION_WITH_MEMBERS_INTEGRATION_TESTING = IntegrationTesting(
    bases=(CPSKIN_WITH_MEMBERS_MIGRATION_FIXTURE, ),
    name="CPSKIN_MIGRATION_WITH_MEMBERS_INTEGRATION_TESTING")

CPSKIN_MIGRATION_FUNCTIONAL_TESTING = FunctionalTesting(
    bases=(CPSKIN_MIGRATION_FIXTURE, ),
    name="CPSKIN_MIGRATION_INTEGRATION_TESTING")
