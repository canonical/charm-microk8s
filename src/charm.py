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
    def join_url(self):
        """Retrieve join URL for local unit."""
        join_urls = json.loads(self.relation.data[self.app].get('join_urls', '{}'))
        return join_urls.get(self._local_unit.name)

    @join_url.setter
    def join_url(self, url):
        """Record join URL for remote unit."""
        join_urls = json.loads(self.relation.data[self.app].get('join_urls', '{}'))
        if self.unit.name in join_urls:
            raise MultipleJoinError('{} is already joined to this cluster'.format(self.unit.name))
        join_urls[self.unit.name] = url
        self.relation.data[self.app]['join_urls'] = json.dumps(join_urls)

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
    """charm runs add-node in response to this event, passes join URL back somehow"""
    pass


class MicroK8sClusterNodeAddedEvent(MicroK8sClusterEvent):
    """charm runs join in response to this event using supplied join URL"""
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
        if not event.unit:
            return
        if event.unit not in event.relation.data:
            logger.error('Received event for {} that has no relation data!  Please file a bug.'.format(event.unit.name))
            return
        if self.model.unit.is_leader():
            join_urls = json.loads(event.relation.data[event.app].get('join_urls', '{}'))
            if not join_urls:
                logger.debug('We are the seed node.')
                # The seed node is implicitly joined, so there's no need to emit an event.
                self._state.joined = True
            if event.unit.name in join_urls:
                logger.debug('Already added {} to the cluster.'.format(event.unit.name))
                return
            logger.info('Adding {} to the cluster.'.format(event.unit.name))
            self.on.add_unit.emit(**self._event_args(event))
        else:
            if self._state.joined:
                return
            if 'join_urls' not in event.relation.data[event.app]:
                return
            join_urls = json.loads(event.relation.data[event.app]['join_urls'])
            if self.model.unit.name not in join_urls:
                logger.debug('No join URL for {} yet.'.format(self.model.unit.name))
                return
            logger.info('We have a join URL.')
            self.on.node_added.emit(**self._event_args(event))
            self._state.joined = True


class MicroK8sCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        self.cluster = MicroK8sCluster(self, 'cluster')
        self.framework.observe(self.cluster.on.add_unit, self._on_add_unit)
        self.framework.observe(self.cluster.on.node_added, self._on_node_added)

    def _on_add_unit(self, event):
        logger.info('MICROK8S: ran add-node, got join URL')
        event.join_url = 'join URL for {}'.format(event.unit.name)

    def _on_node_added(self, event):
        url = event.join_url
        logger.info('MICROK8S: run join with {}'.format(url))

    def _on_config_changed(self, _):
        logger.info('MICROK8S: no config yet')

    def _on_install(self, _):
        logger.info('MICROK8S: snap install --classic microk8s')


if __name__ == "__main__":
    main(MicroK8sCharm, use_juju_for_storage=True)
