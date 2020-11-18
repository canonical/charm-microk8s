#!/usr/bin/env python3
# Copyright 2020 Paul Collins
# See LICENSE file for licensing details.

import json
import logging

from ops.charm import CharmBase
from ops.main import main
from ops.framework import Object, StoredState

logger = logging.getLogger(__name__)


class Microk8sCharm(CharmBase):
    _state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self._state.set_default(joined=False)

        self.framework.observe(self.on['cluster'].relation_broken, self._on_cluster_relation)
        self.framework.observe(self.on['cluster'].relation_changed, self._on_cluster_relation)
        self.framework.observe(self.on['cluster'].relation_departed, self._on_cluster_relation)
        self.framework.observe(self.on['cluster'].relation_joined, self._on_cluster_relation)
                  
    def _on_cluster_relation(self, event):
        # On application relation settings: https://bugs.launchpad.net/juju/+bug/1869915/comments/1
        # Remember: reads are remote and writes are local!
        #
        # So, we'll:
        #  - load "joins" from application settings
        #  - check to see if there's a join for the remote unit
        #  - if there isn't, run `add-node`, store joins in app settings, store joins in relation unit settings
        #
        # We also must handle "seeding" the cluster.  We can tell if we need to do this by "joins" being absent from the relation's application settings.
        if not event.unit:
            logger.info('MICROK8S: no event.unit! passing')
            return
        if event.unit not in event.relation.data:
            logger.error('MICROK8S: event for {} but no relation data!'.format(event.unit.name))
            return
        if self.model.unit.is_leader():
            joins = json.loads(event.relation.data[self.app].get('joins', '{}'))
            if not joins:
                logger.info('MICROK8S: joins is empty! we are the seed node')
                # We MUST be the seed node, right?
                self._state.joined = True
            if event.unit.name in joins:
                logger.info('MICROK8S: already joined {}'.format(event.unit.name))
                return
            logger.info('MICROK8S: joining {}'.format(event.unit.name))
            joins[event.unit.name] = 'JOIN {}'.format(event.unit.name)
            event.relation.data[self.app]['joins'] = json.dumps(joins)
            event.relation.data[self.model.unit]['joins'] = json.dumps(joins)
        else:
            if self._state.joined:
                logger.info('MICROK8S: already joined - exiting')
                return
            if 'joins' not in event.relation.data[event.unit]:
                logger.info('MICROK8S: not joined and no joins in relation data - exiting')
                return
            joins = json.loads(event.relation.data[event.unit]['joins'])
            if self.model.unit.name not in joins:
                logger.info('MICROK8S: no join yet!')
                return
            logger.info('MICROK8S: WE HAVE A JOIN! {}'.format(joins[self.model.unit.name]))
            self._state.joined = True

    def _on_config_changed(self, _):
        logger.info('MICROK8S: no config yet')

    def _on_install(self, _):
        logger.info('MICROK8S: snap install --classic microk8s')


if __name__ == "__main__":
    main(Microk8sCharm, use_juju_for_storage=True)
