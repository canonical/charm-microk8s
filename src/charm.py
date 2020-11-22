#!/usr/bin/env python3
# Copyright 2020 Paul Collins
# See LICENSE file for licensing details.

import json
import logging
import socket
import subprocess

from ops.charm import CharmBase, RelationEvent
from ops.main import main
from ops.framework import EventSource, Object, ObjectEvents, StoredState
from ops.model import ActiveStatus, MaintenanceStatus

from utils import get_departing_unit_name, join_url_from_add_node_output

logger = logging.getLogger(__name__)


# FIXME(pjdc): All of the join_urls and hostnames manipulation below should be encapsulated.

class EventError(Exception):
    pass


class MultipleJoinError(Exception):
    pass


class MicroK8sClusterEvent(RelationEvent):
    def __init__(self, handle, relation, app, unit, local_unit, departing_unit_name):
        super().__init__(handle, relation, app, unit)
        self._local_unit = local_unit
        # We capture JUJU_DEPARTING_UNIT so that we can freely defer
        # these events and refer to the value later, even outside a
        # cluster-relation-departed hook context.
        self._departing_unit_name = departing_unit_name

    @property
    def departing_unit_name(self):
        """The unit that is departing this relation."""
        return self._departing_unit_name

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
            dict(
                departing_unit_name=self._departing_unit_name,
                local_unit_name=self._local_unit.name,
            ),
        ]
        return s

    def restore(self, snapshot):
        sup, mine = snapshot
        super().restore(sup)
        # NOTE(pjdc): How is self.framework not set in __init__ but set here?!
        self._local_unit = self.framework.model.get_unit(mine["local_unit_name"])
        self._departing_unit_name = mine['departing_unit_name']


class MicroK8sClusterNewNodeEvent(MicroK8sClusterEvent):
    """charm runs add-node in response to this event, passes join URL back somehow"""
    pass


class MicroK8sClusterNodeAddedEvent(MicroK8sClusterEvent):
    """charm runs join in response to this event using supplied join URL"""
    pass


class MicroK8sClusterOtherNodeRemovedEvent(MicroK8sClusterEvent):
    """Another unit has been removed from the cluster.

    This event is never emitted on the departing unit."""
    pass


class MicroK8sClusterThisNodeRemovedEvent(MicroK8sClusterEvent):
    """This unit has been removed from the cluster.

    This event is only emitted on the departing unit."""
    pass


class MicroK8sClusterEvents(ObjectEvents):
    add_unit = EventSource(MicroK8sClusterNewNodeEvent)
    node_added = EventSource(MicroK8sClusterNodeAddedEvent)
    other_node_removed = EventSource(MicroK8sClusterOtherNodeRemovedEvent)
    this_node_removed = EventSource(MicroK8sClusterThisNodeRemovedEvent)


class MicroK8sCluster(Object):
    on = MicroK8sClusterEvents()
    _state = StoredState()

    def __init__(self, charm, relation_name):
        super().__init__(charm, relation_name)
        self.relation_name = relation_name
        self._state.set_default(joined=False)

        self.framework.observe(charm.on[relation_name].relation_changed, self._on_relation_changed)
        self.framework.observe(charm.on[relation_name].relation_departed, self._on_relation_departed)

    def _event_args(self, relation_event):
        return dict(
            relation=relation_event.relation,
            app=relation_event.app,
            unit=relation_event.unit,
            local_unit=self.model.unit,
            departing_unit_name=get_departing_unit_name(),
        )

    def _on_relation_changed(self, event):
        if not event.unit:
            return
        if event.unit not in event.relation.data:
            logger.error('Received event for {} that has no relation data!  Please file a bug.'.format(event.unit.name))
            return

        # Identify ourselves to other units.
        our_hostname = socket.gethostname()
        event.relation.data[self.model.unit]['hostname'] = our_hostname

        if self.model.unit.is_leader():
            hostnames = json.loads(event.relation.data[event.app].get('hostnames', '{}'))
            # We're the leader, so we have to self-identify.
            hostnames[self.model.unit.name] = our_hostname
            if 'hostname' in event.relation.data[event.unit]:
                hostnames[event.unit.name] = event.relation.data[event.unit]['hostname']
            event.relation.data[event.app]['hostnames'] = json.dumps(hostnames)

            join_urls = json.loads(event.relation.data[event.app].get('join_urls', '{}'))
            if not join_urls:
                logger.debug('We are the seed node.')
                # The seed node is implicitly joined, so there's no need to emit an event.
                self._state.joined = True
            if event.unit.name in join_urls:
                logger.debug('Already added {} to the cluster.'.format(event.unit.name))
                return
            logger.debug('Add {} to the cluster, emitting event.'.format(event.unit.name))
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
            logger.debug('We have a join URL, emitting event.')
            self.on.node_added.emit(**self._event_args(event))
            self._state.joined = True

    def _on_relation_departed(self, event):
        """Clean up the remnants of a removed unit."""
        if not event.unit:
            return

        departing_unit_name = get_departing_unit_name()
        if not departing_unit_name:
            raise EventError('BUG: relation-departed event with departing_unit_name not available!')

        if self.model.unit.name == departing_unit_name:
            self.on.this_node_removed.emit(**self._event_args(event))
        else:
            self.on.other_node_removed.emit(**self._event_args(event))


class MicroK8sCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)

        self.cluster = MicroK8sCluster(self, 'cluster')
        self.framework.observe(self.cluster.on.add_unit, self._on_add_unit)
        self.framework.observe(self.cluster.on.node_added, self._on_node_added)
        self.framework.observe(self.cluster.on.other_node_removed, self._on_other_node_removed)
        self.framework.observe(self.cluster.on.this_node_removed, self._on_this_node_removed)

    def _on_add_unit(self, event):
        self.unit.status = MaintenanceStatus('adding {} to the microk8s cluster'.format(event.unit.name))
        output = subprocess.check_output(['/snap/bin/microk8s', 'add-node']).decode('utf-8')
        url = join_url_from_add_node_output(output)
        logger.debug('Generated join URL: {}'.format(url))
        event.join_url = url
        self.unit.status = ActiveStatus()

    def _on_node_added(self, event):
        self.unit.status = MaintenanceStatus('joining the microk8s cluster')
        url = event.join_url
        logger.debug('Using join URL: {}'.format(url))
        subprocess.check_call(['/snap/bin/microk8s', 'join', url])
        self.unit.status = ActiveStatus()

    def _on_other_node_removed(self, event):
        departing_unit = self.framework.model.get_unit(event.departing_unit_name)
        # The unit can disappear from `relation-list` before its
        # `cluster-relation-departed` hook has finished executing, so
        # this doesn't work in all cases... or at all, in my testing.
        if departing_unit and departing_unit in event.relation.units:
            logger.info('{} is still around.  Waiting for it to go away.'.format(event.departing_unit_name))
            event.defer()
        # If the unit has now gone away and was formerly the leader, we assume there is now a new leader.
        if not self.model.unit.is_leader():
            logger.debug('Only the leader should remove nodes from the cluster.')
            return
        hostnames = json.loads(event.relation.data[event.app].get('hostnames', '{}'))
        hostname = hostnames.get(event.departing_unit_name)
        if not hostname:
            logger.error('Cannot remove node: hostname for {} not found.'.format(event.departing_unit_name))
            return
        self.unit.status = MaintenanceStatus('removing {} from the microk8s cluster'.format(event.departing_unit_name))
        logger.debug('Removing {} (hostname {}) from the cluster.'.format(event.departing_unit_name, hostname))
        subprocess.check_call(['/snap/bin/microk8s', 'remove-node', hostname])
        self.unit.status = ActiveStatus()

    def _on_this_node_removed(self, event):
        self.unit.status = MaintenanceStatus('leaving the microk8s cluster')
        subprocess.check_call(['/snap/bin/microk8s', 'leave'])
        self.unit.status = ActiveStatus()

    def _on_install(self, _):
        self.unit.status = MaintenanceStatus('installing microk8s')
        subprocess.check_call(['/usr/bin/snap', 'install', '--classic', 'microk8s'])
        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(MicroK8sCharm, use_juju_for_storage=True)
