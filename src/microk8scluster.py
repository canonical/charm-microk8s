import logging
import subprocess

from ops.charm import RelationEvent
from ops.framework import EventSource, Object, ObjectEvents, StoredState
from ops.model import ActiveStatus, MaintenanceStatus

from etchosts import refresh_etc_hosts
from hostnamemanager import HostnameManager
from portmanager import PortManager

from utils import (
    addon_relation_key,
    get_departing_unit_name,
    get_microk8s_node,
    get_microk8s_nodes_json,
    join_url_from_add_node_output,
    join_url_key,
)

logger = logging.getLogger(__name__)


DEFAULT_ADDONS = ['dns', 'ingress']


class EventError(Exception):
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
    def join_complete(self):
        return self.relation.data[self.unit].get('join_complete')

    @join_complete.setter
    def join_complete(self, complete):
        self.relation.data[self._local_unit]['join_complete'] = complete

    @property
    def join_url(self):
        """Retrieve join URL for local unit."""
        return self.relation.data[self.app].get(join_url_key(self._local_unit))

    @join_url.setter
    def join_url(self, url):
        """Record join URL for remote unit."""
        self.relation.data[self.app][join_url_key(self.unit)] = url

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


class MicroK8sClusterIngressAddonEnabledEvent(MicroK8sClusterEvent):
    """The ingress addon has been enabled."""


class MicroK8sClusterJoinCompleteEvent(MicroK8sClusterEvent):
    """A unit has successfully executed `microk8s join`."""


class MicroK8sClusterNodeAddedEvent(MicroK8sClusterEvent):
    """charm runs join in response to this event using supplied join URL"""


class MicroK8sClusterOtherNodeRemovedEvent(MicroK8sClusterEvent):
    """Another unit has been removed from the cluster.

    This event is never emitted on the departing unit."""


class MicroK8sClusterThisNodeRemovedEvent(MicroK8sClusterEvent):
    """This unit has been removed from the cluster.

    This event is only emitted on the departing unit."""


class MicroK8sClusterEvents(ObjectEvents):
    add_unit = EventSource(MicroK8sClusterNewNodeEvent)
    ingress_addon_enabled = EventSource(MicroK8sClusterIngressAddonEnabledEvent)
    join_complete = EventSource(MicroK8sClusterJoinCompleteEvent)
    node_added = EventSource(MicroK8sClusterNodeAddedEvent)
    other_node_removed = EventSource(MicroK8sClusterOtherNodeRemovedEvent)
    this_node_removed = EventSource(MicroK8sClusterThisNodeRemovedEvent)


class MicroK8sCluster(Object):
    on = MicroK8sClusterEvents()
    _state = StoredState()

    def __init__(self, charm, relation_name):
        super().__init__(charm, relation_name)

        self._state.set_default(
            previous_ingress_addon_state=False,
            joined=False,
        )

        self.hostnames = HostnameManager(charm, relation_name)
        self.ports = PortManager(charm, relation_name)

        self.framework.observe(charm.on.install, self._on_install)

        self.framework.observe(charm.on[relation_name].relation_created, self._set_default_addon_state)
        self.framework.observe(charm.on[relation_name].relation_changed, self._on_relation_changed)
        self.framework.observe(charm.on[relation_name].relation_changed, self._maybe_ingress_enabled)
        self.framework.observe(charm.on[relation_name].relation_departed, self._on_relation_departed)

        self.framework.observe(self.on.add_unit, self._on_add_unit)
        self.framework.observe(self.on.ingress_addon_enabled, self._on_ingress_addon_enabled)
        self.framework.observe(self.on.join_complete, self._update_etc_hosts)
        self.framework.observe(self.on.node_added, self._on_node_added)
        self.framework.observe(self.on.other_node_removed, self._on_other_node_removed)
        self.framework.observe(self.on.this_node_removed, self._on_this_node_removed)

    def _event_args(self, relation_event):
        return dict(
            relation=relation_event.relation,
            app=relation_event.app,
            unit=relation_event.unit,
            local_unit=self.model.unit,
            departing_unit_name=get_departing_unit_name(),
        )

    def _on_install(self, _):
        self.model.unit.status = MaintenanceStatus('installing microk8s')
        subprocess.check_call(['/usr/bin/snap', 'install', '--classic', 'microk8s'])

        if DEFAULT_ADDONS:
            # FIXME(pjdc): This is a waste of time if we're not the
            # seed node, but I'm not sure it's possible to know during
            # the install hook if that's true.  Maybe `goal-state`?
            self.model.unit.status = MaintenanceStatus('enabling microk8s addons')
            cmd = ['/snap/bin/microk8s', 'enable']
            cmd.extend(DEFAULT_ADDONS)
            subprocess.check_call(cmd)
            self.model.unit.status = ActiveStatus()

    def _set_default_addon_state(self, event):
        """Ensure the enabled addons are correctly recorded in the peer relation."""
        if not self.model.unit.is_leader():
            return
        reldata = event.relation.data[event.app]
        for addon in DEFAULT_ADDONS:
            relkey = addon_relation_key(addon)
            if relkey not in reldata:
                reldata[relkey] = 'enabled'
                if addon == 'ingress':
                    self.on.ingress_addon_enabled.emit(**self._event_args(event))

    def _maybe_ingress_enabled(self, event):
        status = event.relation.data[event.app].get(addon_relation_key('ingress'))
        if status == 'enabled' and not self._state.previous_ingress_addon_state:
            self.on.ingress_addon_enabled.emit(**self._event_args(event))
            self._state.previous_ingress_addon_state = True

    def _on_relation_changed(self, event):
        if event.unit and event.relation.data[event.unit].get('join_complete'):
            logger.debug('Join complete on {}.'.format(event.unit.name))
            self.on.join_complete.emit(**self._event_args(event))

        if event.unit and self.model.unit.is_leader():
            keys = [key for key in event.relation.data[event.app].keys() if key.endswith('.join_url')]
            if not keys:
                logger.debug('We are the seed node.')
                # The seed node is implicitly joined, so there's no need to emit an event.
                self._state.joined = True
            if join_url_key(event.unit) in keys:
                logger.debug('Already added {} to the cluster.'.format(event.unit.name))
                return
            logger.debug('Add {} to the cluster, emitting event.'.format(event.unit.name))
            self.on.add_unit.emit(**self._event_args(event))

        else:
            if self._state.joined:
                return
            join_url = event.relation.data[event.app].get(join_url_key(self.model.unit))
            if not join_url:
                logger.debug('No join URL for {} yet.'.format(self.model.unit.name))
                return
            logger.debug('We have a join URL, emitting event.')
            self.on.node_added.emit(**self._event_args(event))

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

    def _on_add_unit(self, event):
        self.model.unit.status = MaintenanceStatus('adding {} to the microk8s cluster'.format(event.unit.name))
        output = subprocess.check_output(['/snap/bin/microk8s', 'add-node']).decode('utf-8')
        url = join_url_from_add_node_output(output)
        logger.debug('Generated join URL: {}'.format(url))
        event.join_url = url
        self.model.unit.status = ActiveStatus()

    def _on_ingress_addon_enabled(self, event):
        if self.model.unit.is_leader():
            self.model.unit.status = MaintenanceStatus('opening ingress ports')
            self.ports.open('80/tcp')
            self.ports.open('443/tcp')
            self.model.unit.status = ActiveStatus()

    def _on_node_added(self, event):
        self.model.unit.status = MaintenanceStatus('joining the microk8s cluster')
        url = event.join_url
        logger.debug('Using join URL: {}'.format(url))
        subprocess.check_call(['/snap/bin/microk8s', 'join', url])
        self._state.joined = True
        event.join_complete = 'true'
        self.model.unit.status = ActiveStatus()
        self.on.join_complete.emit(**self._event_args(event))

    def _on_other_node_removed(self, event):
        departing_unit = self.framework.model.get_unit(event.departing_unit_name)
        # The unit can disappear before its `cluster-relation-departed`
        # hook has finished executing, so this doesn't work in all cases...
        # or perhaps, as in my testing, it doesn't work at all?
        if departing_unit and departing_unit in event.relation.units:
            logger.info('{} is still around.  Waiting for it to go away.'.format(event.departing_unit_name))
            event.defer()
            return
        hostname = self.hostnames.peers.get(event.departing_unit_name)
        if not hostname:
            logger.error('Cannot remove node: hostname for {} not found.'.format(event.departing_unit_name))
            return
        node = get_microk8s_node(hostname)
        if not node.exists():
            logger.debug('Node {} does not exist, nothing to do.'.format(hostname))
            return
        if not self.model.unit.is_leader():
            logger.debug('Waiting for leadership in case it falls on us to delete the node.')
            event.defer()
            return
        if node.ready():
            logger.debug('Node {} is still ready; deferring event.'.format(hostname))
            event.defer()
            return
        self.model.unit.status = MaintenanceStatus('removing {} from the microk8s cluster'.format(
            event.departing_unit_name))
        logger.info('Removing {} (hostname {}) from the cluster.'.format(
            event.departing_unit_name, hostname))
        subprocess.check_call(['/snap/bin/microk8s', 'remove-node', hostname])
        self.model.unit.status = ActiveStatus()

    def _on_this_node_removed(self, event):
        self.model.unit.status = MaintenanceStatus('leaving the microk8s cluster')
        subprocess.check_call(['/snap/bin/microk8s', 'leave'])
        self.model.unit.status = ActiveStatus()

    def _update_etc_hosts(self, event):
        if not self.model.config.get('manage_etc_hosts'):
            return
        if not self._state.joined:
            event.defer()

        self.model.unit.status = MaintenanceStatus('updating /etc/hosts')
        nodes_json = get_microk8s_nodes_json()
        refresh_etc_hosts(nodes_json)
        self.model.unit.status = ActiveStatus()
