# -*- coding: utf-8 -*-
from ..migrate import fix_at_image_scales
from ..migrate import fix_portlets_image_scales
from Acquisition import aq_base
from collective.geo.behaviour.behaviour import Coordinates
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.utils import defaultKeys
from collective.transmogrifier.utils import defaultMatcher
from collective.transmogrifier.utils import Expression
from collective.transmogrifier.utils import Matcher
from collective.transmogrifier.utils import traverse
from copy import deepcopy
from datetime import datetime
from DateTime import DateTime
from eea.facetednavigation.criteria.handler import Criteria
from eea.facetednavigation.widgets.storage import Criterion
from plone import api
from plone.dexterity.interfaces import IDexterityContent
from Products.CMFDynamicViewFTI.interface import ISelectableBrowserDefault
from xml.dom import minidom
from z3c.relationfield.relation import RelationValue
from zope.app.container.contained import notifyContainerModified
from zope.component import getMultiAdapter
from zope.component import getUtility
from zope.component import queryMultiAdapter
from zope.component.interfaces import ComponentLookupError
from zope.component.interfaces import IFactory
from zope.container.interfaces import INameChooser
from zope.intid.interfaces import IIntIds
from zope.interface import alsoProvides
from zope.interface import classProvides
from zope.interface import implementer
from plone.portlets.interfaces import ILocalPortletAssignable
from plone.portlets.interfaces import IPortletManager
from plone.portlets.interfaces import IPortletAssignmentMapping
from plone.portlets.interfaces import ILocalPortletAssignmentManager
from plone.app.portlets.interfaces import IPortletTypeInterface
from plone.app.portlets.exportimport.interfaces import IPortletAssignmentExportImportHandler

from Products.MailHost.interfaces import IMailHost

import base64
import json
import logging
import posixpath
import urllib2
logger = logging.getLogger('Cpskin blueprints')

LISTING_VIEW_MAPPING = {  # OLD (AT and old DX) : NEW
    'all_content': 'full_view',
    'atct_album_view': 'album_view',
    'atct_topic_view': 'listing_view',
    'collection_view': 'listing_view',
    'folder_album_view': 'album_view',
    'folder_full_view': 'full_view',
    'folder_listing': 'listing_view',
    'folder_listing_view': 'listing_view',
    'folder_summary_view': 'summary_view',
    'folder_tabular_view': 'tabular_view',
    'standard_view': 'listing_view',
    'thumbnail_view': 'album_view',
    'view': 'listing_view',
}


def getIfaceById(name):
    components = name.split('.')
    components.reverse()
    try:
        obj = __import__(components.pop())
    except (ImportError, ValueError):
        return None
    while obj is not None and components:
        obj = getattr(obj, components.pop(), None)
    return obj


@implementer(ISection)
class Dexterity(object):
    classProvides(ISectionBlueprint)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.options = options
        self.context = transmogrifier.context if transmogrifier.context else api.portal.get()  # noqa
        self.name = name
        self.ttool = api.portal.get_tool('portal_types')
        self.typekey = defaultMatcher(options, 'type-key', name, 'type',
                                      ('portal_type', 'Type'))
        self.required = bool(options.get('required'))
        self.pathkey = defaultMatcher(options, 'path-key', name, 'path')
        self.poskey = defaultMatcher(options, 'pos-key', name, 'gopip')
        # Position of items without a position value
        self.default_pos = int(options.get('default-pos', 1000000))
        self.fileskey = options.get('files-key', '_files').strip()
        self.disable_constraints = Expression(
            options.get('disable-constraints', 'python: False'),
            transmogrifier,
            name,
            options,
        )

        # if importing from collective.jsonify exported json structures, there
        # is an datafield entry for binary data, which' prefix can be
        # configured.
        self.datafield_prefix = options.get('datafield-prefix', '_datafield_')

        # make site empty
        plonesite = api.portal.get()
        for content in plonesite.contentValues():
            api.content.delete(content)
            logger.info('{0} deleted'.format(content.id))

        # get portal_skins/custom folder
        self.remote_url = self.get_option('remote-url', 'http://localhost:8080')
        remote_username = self.get_option('remote-username', 'admin')
        remote_password = self.get_option('remote-password', 'admin')
        auth_handler = urllib2.HTTPBasicAuthHandler()
        auth_handler.add_password(realm='Zope',
                                  uri=self.remote_url,
                                  user=remote_username,
                                  passwd=remote_password)
        opener = urllib2.build_opener(auth_handler)
        urllib2.install_opener(opener)
        url = '{0}/transmo-export'.format(self.remote_url)
        req = urllib2.Request(url)
        try:
            f = urllib2.urlopen(req)
            resp = f.read()
        except urllib2.URLError:
            raise
        results = json.loads(resp)

        # copy portal_skins/custom folder
        portal_skins = api.portal.get_tool('portal_skins')
        custom_folder = portal_skins.custom
        for result in results.get('custom', []):
            meta_type = result.get('meta_type')
            obj_id = result.get('obj_id')
            if meta_type in ['Image', 'File']:
                data = base64.b64decode(result.get('data'))
                add_meta = 'manage_add{0}'.format(meta_type.replace(' ', ''))
                getattr(custom_folder, add_meta)(obj_id, data)
            else:
                raw = result.get('raw', None)

            if obj_id not in custom_folder.keys():
                logger.info('add {}'.format(obj_id))
                add_meta = 'manage_add{0}'.format(meta_type.replace(' ', ''))
                if raw:
                    getattr(custom_folder, add_meta)(obj_id)
                    obj = custom_folder.get(obj_id)
                    obj.munge(raw.encode('utf8'))

        # install packages not installed
        portal_quickinstaller = api.portal.get_tool('portal_quickinstaller')
        product_ids = [
            product['id'] for product in portal_quickinstaller.listInstalledProducts()]
        blacklist = ['collective.contentleadimage', 'plone.app.collection', 'cpskin.demo']
        for product in results.get('products', []):
            if product not in product_ids and product not in blacklist:
                logger.info('install {}'.format(product))
                portal_quickinstaller.installProduct(product)
        # groups
        for group in results.get('groups', []):
            if not api.group.get(group['id']):
                logger.info('Add group {}'.format(group['id']))
                api.group.create(
                    groupname=group['id'],
                    title=group['title'],
                    description=group['description'],
                    roles=group['roles'],
                    groups=group['groups']
                )
        # users
        for user in results.get('users', []):
            if not api.user.get(user['id']):

                try:
                    api.user.create(
                        username=user['id'],
                        password=user['password'],
                        email=user['email'],
                        roles=user['roles'],
                        properties={
                            'domains': user['domains'],
                            'fullname': user['fullname']
                        }
                    )
                    logger.info('Added user {}'.format(user['id']))
                except ValueError:
                    from imio.helpers.security import generate_password
                    password = generate_password()
                    api.user.create(
                        username=user['id'],
                        password=password,
                        email=user['email'],
                        roles=user['roles'],
                        properties={
                            'domains': user['domains'],
                            'fullname': user['fullname']
                        }
                    )
                    logger.info('New password for user {} => {}'.format(
                        user['id'], password))
        # mailhost
        if results.get('mailhost', False):
            mailhost = results.get('mailhost')
            try:
                mail_host = getUtility(IMailHost)
            except ComponentLookupError:
                mail_host = getattr(api.portal.get(), 'MailHost')
            mail_host.smtp_host = mailhost['smtp_host']
            mail_host.smtp_port = mailhost['smtp_port']
            if mailhost.get('smtp_userid', None):
                mail_host.smtp_userid = mailhost['smtp_userid']
            mail_host.smtp_uid = mailhost['smtp_uid']
            mail_host.smtp_pwd = mailhost['smtp_pwd']
            plonesite.email_from_address = mailhost['email_from_address']
            plonesite.email_from_name = mailhost['email_from_name']
            logger.info('Mailhost updated')

        # geo
        if results.get('geo', False):
            geo = results.get('geo', False)
            lat_key = 'collective.geo.settings.interfaces.IGeoSettings.latitude'
            lng_key = 'collective.geo.settings.interfaces.IGeoSettings.longitude'
            if geo.get('latitude', False) and geo.get('longitude', False):
                from decimal import Decimal
                api.portal.set_registry_record(lat_key, Decimal(geo['latitude']))
                api.portal.set_registry_record(lng_key, Decimal(geo['longitude']))
                logger.info('Geo site settings for latitude and longitude updated.')

        # set cpskin interfaces and title for Plone Site object
        url = '{0}/get_item'.format(self.remote_url)
        req = urllib2.Request(url)
        try:
            f = urllib2.urlopen(req)
            resp = f.read()
        except urllib2.URLError:
            raise
        remote_plone_site = json.loads(resp)
        if remote_plone_site.get('cpskin_interfaces', False):
            for interface_name in remote_plone_site.get('cpskin_interfaces'):
                logger.info('set interface: {}'.format(interface_name))
                alsoProvides(plonesite, getIfaceById(interface_name))
        if remote_plone_site.get('title', False):
            logger.info('set title: {}'.format(remote_plone_site.get('title')))
            plonesite.title = remote_plone_site.get('title')

        # portlets are added at the end because of ConstraintNotSatisfied error
        # indeed porlet content should be added when content is already added
        self.src_portlets = remote_plone_site.get('portlets', False)
        self.src_plonesite = plonesite

    def importAssignment(self, obj, node):
        """ Import an assignment from a node
        """
        # 1. Determine the assignment mapping and the name
        manager_name = node.getAttribute('manager')

        manager = getUtility(IPortletManager, manager_name)
        mapping = getMultiAdapter((obj, manager), IPortletAssignmentMapping)
        if mapping is None:
            return

        # 2. Either find or create the assignment
        assignment = None
        name = node.getAttribute('name')
        if name:
            assignment = mapping.get(name, None)

        type_ = node.getAttribute('type')

        if assignment is None:
            portlet_factory = getUtility(IFactory, name=type_)
            assignment = portlet_factory()

            if not name:
                chooser = INameChooser(mapping)
                name = chooser.chooseName(None, assignment)

            mapping[name] = assignment

        # aq-wrap it so that complex fields will work
        assignment = assignment.__of__(obj)

        # 3. Use an adapter to update the portlet settings
        portlet_interface = getUtility(IPortletTypeInterface, name=type_)
        assignment_handler = IPortletAssignmentExportImportHandler(assignment)
        assignment_handler.import_assignment(portlet_interface, node)

    def importBlacklist(self, obj, node):
        """ Import a blacklist from a node
        """
        manager = node.getAttribute('manager')
        category = node.getAttribute('category')
        status = node.getAttribute('status')

        manager = getUtility(IPortletManager, name=manager)

        assignable = queryMultiAdapter((obj, manager), ILocalPortletAssignmentManager)

        if status.lower() == 'block':
            assignable.setBlacklistStatus(category, True)
        elif status.lower() == 'show':
            assignable.setBlacklistStatus(category, False)
        elif status.lower() == 'acquire':
            assignable.setBlacklistStatus(category, None)

    def get_option(self, name, default):
        """Get an option from the request if available and fallback to the
        transmogrifier config.
        """
        request = getattr(self.context, 'REQUEST', None)
        if request is not None:
            value = request.form.get('form.widgets.' + name.replace('-', '_'),
                                     self.options.get(name, default))
        else:
            value = self.options.get(name, default)
        if isinstance(value, unicode):
            value = value.encode('utf8')
        return value

    def __iter__(self):
        positions_mapping = {}
        default_pages = {}
        atrefs = {}
        for item in self.previous:
            keys = item.keys()
            typekey = self.typekey(*keys)[0]
            pathkey = self.pathkey(*keys)[0]
            poskey = self.poskey(*keys)[0]
            if not (pathkey and typekey and poskey):
                logger.warn('Not enough info for item: %s' % item)
                yield item
                continue

            # remove plone site path from path
            cut = 2
            if self.remote_url.split('/')[-2] == self.remote_url.split('/')[-1]:
                cut = 3
            path_without_plone = '/'+'/'.join(item.get('_path').split('/')[cut:])
            item['_path'] = path_without_plone

            #--- field corrector ---
            if item.get('startDate', False):
                item['start'] = item.get('startDate')
            if item.get('endDate', False):
                item['end'] = item.get('endDate')
            # Dublin core
            if item.get('expirationDate', False):
                item['expires'] = item.get('expirationDate')
            if item.get('effectiveDate', False):
                item['effective'] = item.get('effectiveDate')

            #--- constructor ---
            type_, path = item[typekey], item[pathkey]
            fti = self.ttool.getTypeInfo(type_)
            if fti is None:
                logger.warn('Not an existing type: %s' % type_)
                yield item; continue

            path = path.encode('ASCII')
            container, id = posixpath.split(path.strip('/'))
            context = traverse(self.context, container, None)
            if context is None:
                error = 'Container %s does not exist for item %s' % (
                    container, path)
                if self.required:
                    raise KeyError(error)
                logger.warn(error)
                yield item
                continue

            if getattr(aq_base(context), id, None) is not None:  # item exists
                yield item; continue
            obj = fti._constructInstance(context, id)

            # For CMF <= 2.1 (aka Plone 3)
            if hasattr(fti, '_finishConstruction'):
                obj = fti._finishConstruction(obj)

            if obj.getId() != id:
                item[pathkey] = posixpath.join(container, obj.getId())


            #--- cpskin stuff ---

            # Exclude from nav
            if item.get('excludeFromNav', False):
                obj.exclude_from_nav = item.get('excludeFromNav')

            if item.get('hiddenTags', False):
                obj.hiddenTags = item.get('hiddenTags')

            if item.get('standardTags', False):
                obj.standardTags = item.get('standardTags')

            if item.get('iamTags', False):
                obj.iamTags = item.get('iamTags')

            if item.get('isearchTags', False):
                obj.isearchTags = item.get('isearchTags')

            if item.get('language', False):
                obj.language = item.get('language')

            if item.get('cpskin_interfaces', False):
                for interface_name in item.get('cpskin_interfaces'):
                    alsoProvides(obj, getIfaceById(interface_name))

            # faceted
            if item.get('faceted_interfaces', False):
                for interface_name in item.get('faceted_interfaces'):
                    alsoProvides(obj, getIfaceById(interface_name))

            if item.get('faceted_criteria', False):
                crits = item.get('faceted_criteria')
                criteria = Criteria(obj)
                criterions = []
                new_criterias = []
                for crit in crits:
                    criterion = Criterion(**crit)
                    criterions.append(criterion)
                criteria._update(criterions)

            # coord
            if item.get('coordinates', False):
                coord = item.get('coordinates')
                new_coord = Coordinates(obj)
                obj.coordinates = coord

            # Put creation and modification time on its place
            if item.get('creation_date', False):
                if IDexterityContent.providedBy(item):
                    obj.creation_date = datetime.strptime(
                        item.get('creation_date'), '%Y-%m-%d %H:%M')
                else:
                    obj.creation_date = DateTime(item.get('creation_date'))

            if item.get('modification_date', False):
                if IDexterityContent.providedBy(obj):
                    obj.modification_date = datetime.strptime(
                        item.get('modification_date'), '%Y-%m-%d %H:%M')
                else:
                    obj.creation_date = DateTime(item.get('modification_date'))

            # Set subjects
            if item.get('subject', False):
                obj.setSubject(item['subject'])

            # layout
            if ISelectableBrowserDefault.providedBy(obj):
                layout = item.get('_layout', None)
                defaultpage = item.get('_defaultpage', None)
                if layout:
                    default_view = LISTING_VIEW_MAPPING.get(layout)
                    if not default_view:
                        default_view = layout
                    obj.setLayout(str(default_view))

                if defaultpage:
                    obj.setDefaultPage(str(defaultpage))
                    if defaultpage != 'index_html':
                        default_pages[item[pathkey]] = str(defaultpage)

            # portlets
            if item.get('portlets, None') and ILocalPortletAssignable.providedBy(obj):
                data = None
                data = item['portlets']
                doc = minidom.parseString(data)
                root = doc.documentElement
                for elem in root.childNodes:
                    if elem.nodeName == 'assignment':
                        self.importAssignment(obj, elem)
                    elif elem.nodeName == 'blacklist':
                        self.importBlacklist(obj, elem)
                fix_portlets_image_scales(obj)
            # Store positions in a mapping containing an id to position mapping for
            # each parent path {parent_path: {item_id: item_pos}}.
            item_id = item[pathkey].split('/')[-1]
            parent_path = '/'.join(item[pathkey].split('/')[:-1])
            if parent_path not in positions_mapping:
                positions_mapping[parent_path] = {}

            positions_mapping[parent_path][item_id] = item[poskey]

            # atrefs
            if item.get('_atrefs', False):
                atrefs[path] = {}
                for atref in item.get('_atrefs').keys():
                    atrefs[path][atref] = item.get('_atrefs').get(atref)

            yield item

        for path, atref_dict in atrefs.items():
            obj = api.content.get(str(path))
            for ref_key, ref_paths in atref_dict.items():
                # if it's relatedItems reference
                if ref_key == 'relatesTo':
                    rvs = []
                    for ref_path in ref_paths:
                        ref_obj = api.content.get(str(ref_path))
                        intids = getUtility(IIntIds)
                        to_id = intids.getId(ref_obj)
                        rv = RelationValue(to_id)
                        rvs.append(rv)
                    setattr(obj, 'relatedItems', rvs)

        for path, positions in positions_mapping.items():
            # Normalize positions
            ordered_keys = sorted(positions.keys(), key=lambda x: positions[x])
            normalized_positions = {}
            for pos, key in enumerate(ordered_keys):
                normalized_positions[key] = pos

            # TODO: After the new collective.transmogrifier release (>1.4), the
            # utils.py provides a traverse method.
            parent = traverse(self.context, path)
            # parent = self.context.unrestrictedTraverse(path.lstrip('/'))
            if not parent:
                continue
            parent_base = aq_base(parent)

            if hasattr(parent_base, 'getOrdering'):
                ordering = parent.getOrdering()
                # Only DefaultOrdering of p.folder is supported
                if (not hasattr(ordering, '_order')
                        and not hasattr(ordering, '_pos')):
                    continue
                order = ordering._order()
                pos = ordering._pos()
                order.sort(key=lambda x: normalized_positions.get(
                    x, pos.get(x, self.default_pos)))
                for i, id_ in enumerate(order):
                    pos[id_] = i

                notifyContainerModified(parent)

            if parent_base.portal_type == 'Plone Site':
                for ordered_key in ordered_keys:
                    parent_base.moveObjectsToBottom(ordered_key)

        if self.src_portlets:
            if ILocalPortletAssignable.providedBy(self.src_plonesite):
                data = None
                data = self.src_portlets
                doc = minidom.parseString(data.encode('utf8'))
                root = doc.documentElement
                for elem in root.childNodes:
                    if elem.nodeName == 'assignment':
                        logger.info('Assign portlets to plone site')
                        self.importAssignment(self.src_plonesite, elem)
                    elif elem.nodeName == 'blacklist':
                        logger.info('Add blacklist portlets to plone site')
                        self.importBlacklist(self.src_plonesite, elem)
                fix_portlets_image_scales(self.src_plonesite)

        logger.info('Fix at image scales')
        fix_at_image_scales()

        for path, default_page in default_pages.items():
            obj = api.content.get(path)
            obj.setDefaultPage(default_page)
            logger.info('Set default page: {} for: {}'.format(default_page, path))


@implementer(ISection)
class WorkflowHistory(object):
    classProvides(ISectionBlueprint)

    def __init__(self, transmogrifier, name, options, previous):
        self.transmogrifier = transmogrifier
        self.name = name
        self.options = options
        self.previous = previous
        self.context = transmogrifier.context
        self.wftool = api.portal.get_tool('portal_workflow')
        self.pathkey = defaultMatcher(options, 'path-key', name, 'path')

        if 'workflowhistory-key' in options:
            workflowhistorykeys = options['workflowhistory-key'].splitlines()
        else:
            workflowhistorykeys = defaultKeys(options['blueprint'], name, 'workflow_history')
        self.workflowhistorykey = Matcher(*workflowhistorykeys)

    def __iter__(self):
        for item in self.previous:
            pathkey = self.pathkey(*item.keys())[0]
            workflowhistorykey = self.workflowhistorykey(*item.keys())[0]

            if not pathkey or not workflowhistorykey or \
               workflowhistorykey not in item:  # not enough info
                yield item; continue

            obj = self.context.unrestrictedTraverse(str(item[pathkey]).lstrip('/'), None)
            if obj is None or not getattr(obj, 'workflow_history', False):
                yield item; continue

            if IDexterityContent.providedBy(obj):
                item_tmp = deepcopy(item)
                workflow_for_obj = self.wftool.getWorkflowsFor(obj)
                if not workflow_for_obj:
                    yield item; continue
                current_obj_wf = workflow_for_obj[0].id

                # get back datetime stamp and set the workflow history
                for workflow in item_tmp[workflowhistorykey]:
                    for k, workflow2 in enumerate(item_tmp[workflowhistorykey][workflow]):
                        if 'time' in item_tmp[workflowhistorykey][workflow][k]:
                            item_tmp[workflowhistorykey][workflow][k]['time'] = DateTime(item_tmp[workflowhistorykey][workflow][k]['time'])

                if 'cpskin_workflow' in item_tmp[workflowhistorykey].keys():
                    cpskin_workflow = item_tmp[workflowhistorykey]['cpskin_workflow'][-1]
                    review_state = cpskin_workflow.get('review_state')
                    api.content.transition(obj, to_state=review_state)
                obj.workflow_history.data = item_tmp[workflowhistorykey]

                # update security
                workflows = self.wftool.getWorkflowsFor(obj)
                for workfl in workflows:
                    workfl.updateRoleMappingsFor(obj)

            yield item