# -*- coding: utf-8 -*-


def cleanupRegistry(context):
    OLD_STEPS = ['acptheme.cpskin3.uninstall',
                 'acptheme.cpskin3.extra',
                 'acptheme.cpskin3.various',
                 'cpskin.migration.after',
                 'directory-Update-RoleMappings',
                 'directory-postInstall',
                 'directory-Hide-Tools-From-Navigation',
                 'directory-remove-profile',
                 'remember-uninstall',
                 'directory-remove-profile']
    registry = context.getImportStepRegistry()
    for old_step in OLD_STEPS:
        if old_step in registry.listSteps():
            registry.unregisterStep(old_step)
            # Unfortunately we manually have to signal the context
            # (portal_setup) that it has changed otherwise this change is
            # not persisted.
            context._p_changed = True
