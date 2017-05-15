.. contents::

Introduction
============

Migration package for cpskin


Tests
=====

This package is tested using Travis CI. The current status is :

.. image:: https://travis-ci.org/IMIO/cpskin.migration.png
    :target: http://travis-ci.org/IMIO/cpskin.migration




exrample of cpskin/migration/blueprints/dexterity.cfg

.. code-block:: buildout

  [transmogrifier]
  pipeline =
      catalogsource
      skip-plonesite
      setuuid
      folders
      cpskin
      schemaupdater
      owner
      workflow
      logger

  [catalogsource]
  blueprint = collective.jsonmigrator.catalogsource
  remote-url = http://localhost:8080/Plone
  remote-username = admin
  remote-password = admin
  catalog-path = /portal_catalog
  catalog-query = {}

  [skip-plonesite]
  blueprint = collective.transmogrifier.sections.condition
  condition = python:item.get('_type', None) != 'Plone Site'

  [setuuid]
  blueprint = collective.transmogrifier.sections.manipulator
  keys = _uid
  destination = string:plone.uuid

  [folders]
  blueprint = collective.transmogrifier.sections.folders
  path-key = _path

  [cpskin]
  blueprint = cpskin.migration.blueprints.transmo.dexterity
  remote-url = http://localhost:8080/Plone
  remote-username = admin
  remote-password = admin
  path-key = _path
  pos-key = _gopip
  keys =
      _type
      _path
      _gopip

  [schemaupdater]
  blueprint = cpskin.migration.blueprint.transmo.schemaupdater
  path-key = _path

  [owner]
  blueprint = collective.jsonmigrator.owner
  owner-key = _owner
  path-key = _path

  [workflow]
  blueprint = cpskin.migration.blueprints.transmo.workflow

  [logger]
  blueprint = cpskin.migration.blueprint.logger
  keys =
      _type
      _path

