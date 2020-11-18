#!/usr/bin/env python3
# Copyright 2020 Paul Collins
# See LICENSE file for licensing details.

import json
import logging

from ops.charm import CharmBase, RelationEvent
from ops.main import main
from ops.framework import EventSource, Object, ObjectEvents, StoredState

logger = logging.getLogger(__name__)


class MultipleJoinError(Exception):
    pass


class MicroK8sClusterEvent(RelationEvent):
    def __init__(self, handle, relation, app, unit, local_unit):
        super().__init__(handle, relation, app, unit)
        self._local_unit = local_unit

    @property
    def join_code(self):
        """Retrieve join code for local unit stored by the remote unit."""
        joins = json.loads(self.relation.data[self.app].get('joins', '{}'))
        return joins.get(self._local_unit.name)

    @join_code.setter
    def join_code(self, code):
        """Record join code generated for remote unit."""
        joins = json.loads(self.relation.data[self.app].get('joins', '{}'))
        if self.unit.name in joins:
            raise MultipleJoinError('{} is already joined to this cluster'.format(self.unit.name))
        joins[self.unit.name] = code
        self.relation.data[self.app]['joins'] = json.dumps(joins)

    def snapshot(self):
        s = [
            super().snapshot(),
            dict(local_unit_name=self._local_unit.name),
        ]
        return s

    def restore(self, snapshot):
        sup, mine = snapshot
        super().restore(sup)
        self._local_unit = self.framework.model.get_unit(mine["local_unit_name"])


class MicroK8sClusterNewNodeEvent(MicroK8sClusterEvent):
    """charm runs add-node in response to this event, passes join code back somehow"""
    pass


class MicroK8sClusterNodeAddedEvent(MicroK8sClusterEvent):
    """charm runs join in response to this event using supplied join code"""
    pass


class MicroK8sClusterEvents(ObjectEvents):
    add_unit = EventSource(MicroK8sClusterNewNodeEvent)
    node_added = EventSource(MicroK8sClusterNodeAddedEvent)


class MicroK8sCluster(Object):
    on = MicroK8sClusterEvents()
    _state = StoredState()

    def __init__(self, charm, relation_name):
        super().__init__(charm, relation_name)
        self.relation_name = relation_name
        self._state.set_default(joined=False)

        self.framework.observe(charm.on[relation_name].relation_changed, self._on_relation_changed)

    def _event_args(self, relation_event):
        return dict(
            relation=relation_event.relation,
            app=relation_event.app,
            unit=relation_event.unit,
            local_unit=self.model.unit,
        )

    def _on_relation_changed(self, event):
        # On application relation settings: https://bugs.launchpad.net/juju/+bug/1869915/comments/1
        # Remember: reads are remote and writes are local!
        #
        # So, we'll:
        #  - load "joins" from application settings
        #  - check to see if there's a join for the remote unit
        #  - if there isn't, run `add-node`, store joins in app settings, store joins in relation unit settings
        #
        # We also must handle "seeding" the cluster.  We can tell if we need to do this by "joins" being
        # absent from the relation's application settings.
        if not event.unit:
            return
        if event.unit not in event.relation.data:
            logger.critical('MICROK8S: weird event for {} that has no relation data!'.format(event.unit.name))
            return
        if self.model.unit.is_leader():
            joins = json.loads(event.relation.data[event.app].get('joins', '{}'))
            if not joins:
                logger.info('MICROK8S: We are the seed node.')
                self._state.joined = True
                # The seed node is implicity joined, so no event to fire.
            if event.unit.name in joins:
                logger.info('MICROK8S: already joined {}'.format(event.unit.name))
                return
            logger.info('MICROK8S: joining {}'.format(event.unit.name))
            # fire add node event here? then what?
            #   charm code receives add node event
            #   runs add-node
            #   sets join code in event, which updates relation data
            self.on.add_unit.emit(**self._event_args(event))
        else:
            if self._state.joined:
                return
            if 'joins' not in event.relation.data[event.app]:
                return
            joins = json.loads(event.relation.data[event.app]['joins'])
            if self.model.unit.name not in joins:
                logger.info('MICROK8S: no join yet!')
                return
            logger.info('MICROK8S: WE HAVE A JOIN! {}'.format(joins[self.model.unit.name]))
            self.on.node_added.emit(**self._event_args(event))
            self._state.joined = True


class MicroK8sCharm(CharmBase):
    _state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        self.cluster = MicroK8sCluster(self, 'cluster')
        self.framework.observe(self.cluster.on.add_unit, self._on_add_unit)
        self.framework.observe(self.cluster.on.node_added, self._on_node_added)

    def _on_add_unit(self, event):
        logger.info('MICROK8S: ran add-node, got join code')
        event.join_code = 'join code for {}'.format(event.unit.name)

    def _on_node_added(self, event):
        code = event.join_code
        logger.info('MICROK8S: run join with {}'.format(code))

    def _on_config_changed(self, _):
        logger.info('MICROK8S: no config yet')

    def _on_install(self, _):
        logger.info('MICROK8S: snap install --classic microk8s')


if __name__ == "__main__":
    main(MicroK8sCharm, use_juju_for_storage=True)
