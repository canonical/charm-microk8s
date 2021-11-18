import json
import yaml
import logging
import subprocess

from ops.charm import RelationEvent
from ops.framework import EventSource, Object, ObjectEvents, StoredState
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

import kubectl

from etchosts import refresh_etc_hosts
from hostnamemanager import HostnameManager

from utils import (
    check_kubernetes_version_is_older,
    close_port,
    get_departing_unit_name,
    get_microk8s_node,
    get_microk8s_nodes_json,
    join_url_from_add_node_output,
    join_url_key,
    microk8s_ready,
    open_port,
    retry_until_zero_rc,
)

logger = logging.getLogger(__name__)


CONTAINERD_ENV_SNAP_PATH = "/var/snap/microk8s/current/args/containerd-env"


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
        return self.relation.data[self.unit].get("join_complete")

    @join_complete.setter
    def join_complete(self, complete):
        self.relation.data[self._local_unit]["join_complete"] = complete

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
        self._departing_unit_name = mine["departing_unit_name"]


class MicroK8sClusterNewNodeEvent(MicroK8sClusterEvent):
    """charm runs add-node in response to this event, passes join URL back somehow"""


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
            enabled_addons=[],
            joined=False,
        )

        self.hostnames = HostnameManager(charm, relation_name)

        self.framework.observe(charm.on.install, self._on_install)
        self.framework.observe(charm.on.config_changed, self._containerd_env)
        self.framework.observe(charm.on.config_changed, self._coredns_config)
        self.framework.observe(charm.on.config_changed, self._ingress_ports)
        self.framework.observe(charm.on.config_changed, self._manage_addons)
        self.framework.observe(charm.on.config_changed, self._update_etc_hosts)
        self.framework.observe(charm.on.config_changed, self._refresh_channel)

        self.framework.observe(charm.on.start_action, self._microk8s_start)
        self.framework.observe(charm.on.stop_action, self._microk8s_stop)
        self.framework.observe(charm.on.status_action, self._microk8s_status)

        self.framework.observe(charm.on[relation_name].relation_changed, self._on_relation_changed)
        self.framework.observe(charm.on[relation_name].relation_departed, self._on_relation_departed)

        self.framework.observe(self.on.add_unit, self._on_add_unit)
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
        self.model.unit.status = MaintenanceStatus("installing OS packages")
        # OS packages needed by storage providers
        subprocess.check_call(["/usr/bin/apt-get", "install", "--yes", "nfs-common"])
        self.model.unit.status = MaintenanceStatus("installing microk8s")
        channel = self.model.config.get("channel", "auto")
        cmd = "/usr/bin/snap install --classic microk8s".split()
        if channel != "auto":
            cmd.append("--channel={}".format(channel))
        subprocess.check_call(cmd)
        subprocess.check_call(["/usr/sbin/addgroup", "ubuntu", "microk8s"])
        # Required for autocert, useful for the admin.
        subprocess.check_call(["/usr/bin/snap", "alias", "microk8s.kubectl", "kubectl"])
        open_port("16443/tcp")
        self.model.unit.status = ActiveStatus()

    def _manage_addons(self, _):
        if not self.model.unit.is_leader():
            # FIXME(pjdc): Ideally we would record addon state in the
            # peer relation and every unit would defer this event until
            # the requested addons are enabled, or they become leader.
            return

        addons = self.model.config.get("addons", "").split()
        to_enable = [addon for addon in addons if addon not in self._state.enabled_addons]
        to_disable = [addon for addon in self._state.enabled_addons if addon not in addons]

        # FIXME(pjdc): This is a waste of time if we're not the
        # seed node, but I'm not sure it's possible to know during
        # the install hook if that's true. Maybe `goal-state`?
        if to_enable:
            self.model.unit.status = MaintenanceStatus("enabling microk8s addons: {}".format(", ".join(to_enable)))
            cmd = ["/snap/bin/microk8s", "enable"]
            cmd.extend(addons)
            retry_until_zero_rc(cmd, max_tries=10, timeout_seconds=5)
            self.model.unit.status = ActiveStatus()

        if to_disable:
            self.model.unit.status = MaintenanceStatus("disabling microk8s addons: {}".format(", ".join(to_disable)))
            cmd = ["/snap/bin/microk8s", "disable"]
            cmd.extend(to_disable)
            retry_until_zero_rc(cmd, max_tries=10, timeout_seconds=5)
            self.model.unit.status = ActiveStatus()

        self._state.enabled_addons = addons

    def _ingress_ports(self, _):
        addons = self.model.config.get("addons", "").split()
        if "ingress" in addons:
            open_port("80/tcp")
            open_port("443/tcp")
        else:
            close_port("80/tcp")
            close_port("443/tcp")

    def _containerd_env(self, event):
        try:
            with open(CONTAINERD_ENV_SNAP_PATH) as env:
                existing = env.read()
        except Exception:
            # We could be racing install, or who knows what else, so just try again later.
            event.defer()
            return
        configured = self.model.config["containerd_env"]
        if existing == configured:
            return
        # This file is only read on startup, so just truncate and append.
        with open(CONTAINERD_ENV_SNAP_PATH, "w") as env:
            env.write(configured)
            subprocess.check_call(["systemctl", "restart", "snap.microk8s.daemon-containerd.service"])

    def _refresh_channel(self, _):
        channel = self.model.config["channel"]
        if channel == "auto":
            return
        infostr = subprocess.check_output("snap info microk8s".split())
        info = yaml.safe_load(infostr)
        current = info["tracking"]
        if current == channel:
            return

        if check_kubernetes_version_is_older(current, channel):
            self.model.unit.status = BlockedStatus("preventing downgrade from {} to {}".format(current, channel))
            return

        self.model.unit.status = MaintenanceStatus("refreshing to {}".format(channel))
        subprocess.check_call("snap refresh microk8s --channel={}".format(channel).split())
        self.model.unit.status = ActiveStatus()

    def _coredns_config(self, event):
        result = kubectl.get("configmap", "coredns", namespace="kube-system")
        if result.returncode > 0:
            logger.error("Failed to get coredns configmap!  kubectl said: {}".format(result.stderr))
            event.defer()
            return

        configmap = result.stdout
        existing = json.loads(configmap).get("data", {}).get("Corefile")
        configured = self.model.config["coredns_config"]
        if existing == configured:
            logger.info("Nothing to do: contents of coredns_config setting are the same as coredns configmap.")
            return

        if not self.model.unit.is_leader():
            logger.info("There is an update of the coredns configmap pending, but we are not the leader. Deferring.")
            event.defer()
            return

        patch = json.dumps({"data": {"Corefile": configured}})
        result = kubectl.patch("configmap", "coredns", patch, namespace="kube-system")
        if result.returncode > 0:
            logger.error("Failed to patch coredns configmap!  kubectl said: {}".format(result.stderr))
            self.model.status = BlockedStatus("kubectl patch failed updating coredns configmap")
            return

        logger.info("Updated coredns configmap to match coredns_config.")

    def _on_relation_changed(self, event):
        if event.unit and event.relation.data[event.unit].get("join_complete"):
            logger.debug("Join complete on {}.".format(event.unit.name))
            self.on.join_complete.emit(**self._event_args(event))

        if event.unit and self.model.unit.is_leader():
            keys = [key for key in event.relation.data[event.app].keys() if key.endswith(".join_url")]
            if not keys:
                logger.debug("We are the seed node.")
                # The seed node is implicitly joined, so there's no need to emit an event.
                self._state.joined = True
            if join_url_key(event.unit) in keys:
                logger.debug("Already added {} to the cluster.".format(event.unit.name))
                return
            logger.debug("Add {} to the cluster, emitting event.".format(event.unit.name))
            self.on.add_unit.emit(**self._event_args(event))

        else:
            if self._state.joined:
                return
            join_url = event.relation.data[event.app].get(join_url_key(self.model.unit))
            if not join_url:
                logger.debug("No join URL for {} yet.".format(self.model.unit.name))
                return
            logger.debug("We have a join URL, emitting event.")
            self.on.node_added.emit(**self._event_args(event))

    def _on_relation_departed(self, event):
        """Clean up the remnants of a removed unit."""
        if not event.unit:
            return

        departing_unit_name = get_departing_unit_name()
        if not departing_unit_name:
            raise EventError("BUG: relation-departed event with departing_unit_name not available!")

        if self.model.unit.name == departing_unit_name:
            self.on.this_node_removed.emit(**self._event_args(event))
        else:
            self.on.other_node_removed.emit(**self._event_args(event))

    def _on_add_unit(self, event):
        self.model.unit.status = MaintenanceStatus("adding {} to the microk8s cluster".format(event.unit.name))
        output = subprocess.check_output(["/snap/bin/microk8s", "add-node", "--token-ttl", "-1"]).decode("utf-8")
        url = join_url_from_add_node_output(output)
        logger.debug("Generated join URL: {}".format(url))
        event.join_url = url
        self.model.unit.status = ActiveStatus()

    def _on_node_added(self, event):
        self.model.unit.status = MaintenanceStatus("joining the microk8s cluster")
        url = event.join_url
        logger.debug("Using join URL: {}".format(url))
        try:
            subprocess.check_call(["/snap/bin/microk8s", "join", url])
        except subprocess.CalledProcessError:
            logger.error("Failed to join cluster; deferring to try again later.")
            self.model.unit.status = BlockedStatus("join failed, will try again")
            event.defer()
            return
        self._state.joined = True
        event.join_complete = "true"
        self.model.unit.status = ActiveStatus()
        self.on.join_complete.emit(**self._event_args(event))

    def _on_other_node_removed(self, event):
        departing_unit = self.framework.model.get_unit(event.departing_unit_name)
        # The unit can disappear before its `cluster-relation-departed`
        # hook has finished executing, so this doesn't work in all cases...
        # or perhaps, as in my testing, it doesn't work at all?
        if departing_unit and departing_unit in event.relation.units:
            logger.info("{} is still around. Waiting for it to go away.".format(event.departing_unit_name))
            event.defer()
            return
        hostname = self.hostnames.all_peers.get(event.departing_unit_name)
        if not hostname:
            logger.error("Cannot remove node: hostname for {} not found.".format(event.departing_unit_name))
            return
        node = get_microk8s_node(hostname)
        if not node.exists():
            logger.debug("Node {} does not exist, nothing to do.".format(hostname))
            return
        if not self.model.unit.is_leader():
            logger.debug("Waiting for leadership in case it falls on us to delete the node.")
            event.defer()
            return
        if node.ready():
            logger.debug("Node {} is still ready; deferring event.".format(hostname))
            event.defer()
            return
        self.model.unit.status = MaintenanceStatus(
            "removing {} from the microk8s cluster".format(event.departing_unit_name)
        )
        logger.info("Removing {} (hostname {}) from the cluster.".format(event.departing_unit_name, hostname))
        subprocess.check_call(["/snap/bin/microk8s", "remove-node", hostname])
        self.hostnames.forget(event.departing_unit_name)
        self.model.unit.status = ActiveStatus()

    def _on_this_node_removed(self, event):
        self.model.unit.status = MaintenanceStatus("leaving the microk8s cluster")
        subprocess.check_call(["/snap/bin/microk8s", "leave"])
        self.model.unit.status = ActiveStatus()

    def _update_etc_hosts(self, event):
        if not self.model.config.get("manage_etc_hosts"):
            return
        if not self._state.joined:
            logger.info("Waiting for join before updating /etc/hosts")
            event.defer()
            return
        if not microk8s_ready():
            logger.info("Waiting for microk8s to be ready before updating /etc/hosts")
            event.defer()
            return

        self.model.unit.status = MaintenanceStatus("updating /etc/hosts")
        expected_hosts = self.hostnames.peers.values()
        nodes_json = get_microk8s_nodes_json()
        missing = refresh_etc_hosts(nodes_json, expected_hosts)
        if missing:
            logger.error("Not all hosts not found in k8s, deferring event. Missing: {}".format(", ".join(missing)))
            event.defer()
        self.model.unit.status = ActiveStatus()

    def _microk8s_start(self, event):
        subprocess.check_call(["/snap/bin/microk8s", "start"])

    def _microk8s_stop(self, event):
        subprocess.check_call(["/snap/bin/microk8s", "stop"])

    def _microk8s_status(self, event):
        subprocess.check_call(["/snap/bin/microk8s", "status"])
