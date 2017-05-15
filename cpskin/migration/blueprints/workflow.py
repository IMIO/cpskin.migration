# -*- coding: utf-8 -*-
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.utils import defaultKeys
from collective.transmogrifier.utils import defaultMatcher
from collective.transmogrifier.utils import Matcher
from copy import deepcopy
from DateTime import DateTime
from plone import api
from plone.dexterity.interfaces import IDexterityContent
from zope.interface import classProvides
from zope.interface import implementer


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
            workflowhistorykeys = defaultKeys(options['blueprint'], name,
                                              'workflow_history')
        self.workflowhistorykey = Matcher(*workflowhistorykeys)

    def __iter__(self):
        for item in self.previous:
            pathkey = self.pathkey(*item.keys())[0]
            workflowhistorykey = self.workflowhistorykey(*item.keys())[0]

            if not pathkey or not workflowhistorykey or \
               workflowhistorykey not in item:  # not enough info
                yield item
                continue

            obj = self.context.unrestrictedTraverse(
                str(item[pathkey]).lstrip('/'), None)
            if obj is None or not getattr(obj, 'workflow_history', False):
                yield item
                continue

            if IDexterityContent.providedBy(obj):
                item_tmp = deepcopy(item)
                workflow_for_obj = self.wftool.getWorkflowsFor(obj)
                if not workflow_for_obj:
                    yield item
                    continue
                # current_obj_wf = workflow_for_obj[0].id

                # get back datetime stamp and set the workflow history
                for workflow in item_tmp[workflowhistorykey]:
                    for k, workflow2 in enumerate(item_tmp[workflowhistorykey][workflow]):  # noqa
                        if 'time' in item_tmp[workflowhistorykey][workflow][k]:
                            t = DateTime(item_tmp[workflowhistorykey][workflow][k]['time'])  # noqa
                            item_tmp[workflowhistorykey][workflow][k]['time'] = t  # noqa

                if 'cktemplate_workflow' in item_tmp[workflowhistorykey].keys():
                    cktemplate_workflow = item_tmp[workflowhistorykey]['cktemplate_workflow'][-1]  # noqa
                    review_state = cktemplate_workflow.get('review_state')
                    api.content.transition(obj, to_state=review_state)
                if 'cpskin_workflow' not in item_tmp[workflowhistorykey].keys() and 'cpskin3_workflow' in item_tmp[workflowhistorykey].keys():
                    cpskin3_workflow = item_tmp[workflowhistorykey]['cpskin3_workflow'][-1]  # noqa
                    review_state = cpskin3_workflow.get('review_state')
                    api.content.transition(obj, to_state=review_state)
                if 'cpskin_workflow' not in item_tmp[workflowhistorykey].keys() and 'cpskin_moderation_workflow' in item_tmp[workflowhistorykey].keys():
                    cpskin_moderation_workflow = item_tmp[workflowhistorykey]['cpskin_moderation_workflow'][-1]  # noqa
                    review_state = cpskin_moderation_workflow.get('review_state')
                    api.content.transition(obj, to_state=review_state)
                if 'cpskin_workflow' in item_tmp[workflowhistorykey].keys():
                    cpskin_workflow = item_tmp[workflowhistorykey]['cpskin_workflow'][-1]  # noqa
                    review_state = cpskin_workflow.get('review_state')
                    api.content.transition(obj, to_state=review_state)
                obj.workflow_history.data = item_tmp[workflowhistorykey]

                # update security
                workflows = self.wftool.getWorkflowsFor(obj)
                for workfl in workflows:
                    workfl.updateRoleMappingsFor(obj)

            yield item
