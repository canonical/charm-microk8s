#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import json
import logging
import shlex
import socket
import subprocess
import time
from typing import Any, Union

from ops import CharmBase, main
from ops.charm import (
    ConfigChangedEvent,
    InstallEvent,
    LeaderElectedEvent,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
    RelationJoinedEvent,
    RemoveEvent,
    UpdateStatusEvent,
)
from ops.framework import StoredState
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

import microk8s
import util

LOG = logging.getLogger(__name__)


class MicroK8sCharm(CharmBase):
    _state = StoredState()

    def _get_peer_data(self, key: str, default: Any) -> Any:
        if (v := self.model.get_relation("peer").data[self.app].get(key)) is not None:
            return json.loads(v)
        return default

    def _set_peer_data(self, key: str, new_data: Any):
        self.model.get_relation("peer").data[self.app][key] = json.dumps(new_data)

    def __init__(self, *args):
        super().__init__(*args)

        if self.config["role"] not in ["", "worker", "control-plane"]:
            self.unit.status = BlockedStatus("role must be one of '', 'worker', 'control-plane'")
            return

        self._state.set_default(
            role=self.config["role"],
            installed=False,
            joined=False,
            leaving=False,
            join_url="",
            hostnames={},
            hostname=socket.gethostname(),
        )

        if self.config["role"] == "worker":
            self.framework.observe(self.on.remove, self._on_remove)
            self.framework.observe(self.on.install, self._on_install)
            self.framework.observe(self.on.install, self._worker_open_ports)
            self.framework.observe(self.on.config_changed, self._on_config_changed)
            self.framework.observe(self.on.update_status, self._on_update_status)
            self.framework.observe(self.on.microk8s_relation_joined, self._announce_hostname)
            self.framework.observe(self.on.microk8s_relation_joined, self._retrieve_join_url)
            self.framework.observe(self.on.microk8s_relation_changed, self._retrieve_join_url)
            self.framework.observe(self.on.microk8s_relation_broken, self._on_relation_broken)
        else:
            self.framework.observe(self.on.remove, self._on_remove)
            self.framework.observe(self.on.install, self._on_install)
            self.framework.observe(self.on.install, self._on_bootstrap_node)
            self.framework.observe(self.on.install, self._control_plane_open_ports)
            self.framework.observe(self.on.config_changed, self._on_config_changed)
            self.framework.observe(self.on.update_status, self._on_update_status)
            self.framework.observe(self.on.peer_relation_joined, self._add_token)
            self.framework.observe(self.on.peer_relation_joined, self._announce_hostname)
            self.framework.observe(self.on.peer_relation_joined, self._record_hostnames)
            self.framework.observe(self.on.peer_relation_joined, self._retrieve_join_url)
            self.framework.observe(self.on.peer_relation_changed, self._record_hostnames)
            self.framework.observe(self.on.peer_relation_changed, self._retrieve_join_url)
            self.framework.observe(self.on.peer_relation_departed, self._on_relation_departed)
            self.framework.observe(self.on.leader_elected, self._on_config_changed)
            self.framework.observe(self.on.microk8s_provides_relation_joined, self._add_token)
            self.framework.observe(
                self.on.microk8s_provides_relation_changed, self._record_hostnames
            )
            self.framework.observe(
                self.on.microk8s_provides_relation_departed, self._on_relation_departed
            )

    def _record_hostnames(self, event: Union[RelationChangedEvent, RelationJoinedEvent]):
        for unit in event.relation.units:
            hostname = event.relation.data[unit].get("hostname")
            if hostname is not None:
                self._state.hostnames[unit.name] = hostname

    def _on_relation_departed(self, event: RelationDepartedEvent):
        remove_hostname = self._state.hostnames.pop(event.departing_unit.name, None)
        if not self.unit.is_leader():
            return

        if remove_hostname:
            remove_nodes = self._get_peer_data("remove_nodes", [])
            remove_nodes.append(remove_hostname)
            self._set_peer_data("remove_nodes", remove_nodes)

        self._on_config_changed(None)

    def _worker_open_ports(self, _: InstallEvent):
        self.unit.open_port("tcp", 80)
        self.unit.open_port("tcp", 443)

    def _control_plane_open_ports(self, _: InstallEvent):
        self.unit.open_port("tcp", 80)
        self.unit.open_port("tcp", 443)
        self.unit.open_port("tcp", 16443)

    def _on_remove(self, _: RemoveEvent):
        try:
            microk8s.uninstall()
        except subprocess.CalledProcessError:
            LOG.exception("failed to remove microk8s")

    def _announce_hostname(self, event: Union[RelationJoinedEvent, RelationChangedEvent]):
        self._state.hostname = socket.gethostname()
        self._state.hostnames[self.unit.name] = self._state.hostname
        event.relation.data[self.unit]["hostname"] = self._state.hostname

    def _on_install(self, _: InstallEvent):
        if self._state.installed:
            return

        self.unit.status = MaintenanceStatus("installing required packages")
        util.install_required_packages()

        self.unit.status = MaintenanceStatus("installing MicroK8s")
        microk8s.install(self.config["channel"])
        try:
            microk8s.wait_ready()
        except subprocess.CalledProcessError:
            LOG.exception("timed out waiting for node to come up")

        self._state.installed = True
        self._state.joined = False

    def _on_bootstrap_node(self, _: InstallEvent):
        if not self._state.join_url and self.unit.is_leader():
            self._state.joined = True

    def _on_config_changed(self, _: Union[ConfigChangedEvent, LeaderElectedEvent]):
        if self.config["role"] != self._state.role:
            msg = f"role cannot change from '{self._state.role}' after deployment"
            self.unit.status = BlockedStatus(msg)
            return

        if not self._state.installed:
            self._on_install(None)

        if self._state.joined and self.unit.is_leader():
            remove_nodes = self._get_peer_data("remove_nodes", [])

            new_remove_nodes = []
            for hostname in set(remove_nodes):
                # skip self, someone else will remove us when they become leader
                if hostname == self._state.hostname:
                    new_remove_nodes.append(hostname)
                    continue

                self.unit.status = MaintenanceStatus(f"removing node {hostname}")
                try:
                    microk8s.remove_node(hostname)
                except subprocess.CalledProcessError:
                    new_remove_nodes.append(hostname)
                    LOG.exception("failed to remove departing node %s", hostname)

            self._set_peer_data("remove_nodes", new_remove_nodes)

        if self._state.joined and self._state.leaving:
            self.unit.status = MaintenanceStatus("leaving cluster")
            microk8s.uninstall()

            self._state.installed = False
            self._state.joined = False
            self._state.leaving = False
            self._state.join_url = ""

        if not self._state.joined:
            if not self._state.join_url:
                self.unit.status = WaitingStatus("waiting for control plane relation")
                return

            self.unit.status = MaintenanceStatus("joining cluster")
            microk8s.join(self._state.join_url, self.config["role"] == "worker")
            self._state.joined = True

        while self.unit.status.__class__ not in [ActiveStatus]:
            self.unit.status = microk8s.get_unit_status(socket.gethostname())
            time.sleep(5)

    def _on_update_status(self, _: UpdateStatusEvent):
        if self._state.joined:
            self.unit.status = microk8s.get_unit_status(socket.gethostname())

    def _retrieve_join_url(self, event: Union[RelationChangedEvent, RelationJoinedEvent]):
        # TODO(neoaggelos): corner case where the leader in the control plane peer relation changes
        # before other nodes have time to join. deployment might fail in this case.
        if self._state.joined or (self.config["role"] != "worker" and self.unit.is_leader()):
            return

        LOG.info("Looking for join_url from relation %s", event.relation.name)

        join_url = event.relation.data[event.app].get("join_url")
        if not join_url:
            LOG.info("No join_url set yet")
            return

        self._state.join_url = join_url
        self._on_config_changed(None)

    def _on_relation_broken(self, _: RelationBrokenEvent):
        self._state.leaving = True
        LOG.info("Leaving the cluster")
        self._on_config_changed(None)

    def _add_token(self, event: RelationJoinedEvent):
        if not self.unit.is_leader():
            return

        token = microk8s.add_node()

        LOG.info("Generated join token for new node")
        event.relation.data[self.app]["join_url"] = "{}:25000/{}".format(
            self.model.get_binding(event.relation).network.ingress_address, token
        )


if __name__ == "__main__":  # pragma: nocover
    main(MicroK8sCharm, use_juju_for_storage=True)
