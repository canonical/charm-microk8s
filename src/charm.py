#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import logging
import os
import socket
import subprocess
from typing import Union

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
from ops.model import BlockedStatus, MaintenanceStatus, WaitingStatus

import util

LOG = logging.getLogger(__name__)


class MicroK8sCharm(CharmBase):
    _state = StoredState()

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
            remove_nodes=[],
            hostnames={},
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
            self.framework.observe(self.on.leader_elected, self._on_leader_elected)
            self.framework.observe(self.on.microk8s_provides_relation_joined, self._add_token)
            self.framework.observe(
                self.on.microk8s_provides_relation_changed, self._record_hostnames
            )
            self.framework.observe(
                self.on.microk8s_provides_relation_departed, self._on_relation_departed
            )

    def _on_leader_elected(self, _: LeaderElectedEvent):
        # find any nodes that are no longer with us (e.g. old leader control plane) and remove them
        existing_unit_names = set([self.unit.name])

        for relation_name in ["peer", "microk8s-provides"]:
            for r in self.model.relations.get(relation_name) or []:
                existing_unit_names = existing_unit_names.union([u.name for u in r.units])

        for unit_name, hostname in self._state.hostnames.items():
            if unit_name not in existing_unit_names:
                LOG.info("unit %s not found in any relation, will remove", unit_name)
                self._state.remove_nodes.append(hostname)

        self._on_config_changed(None)

    def _record_hostnames(self, event: Union[RelationChangedEvent, RelationJoinedEvent]):
        for unit in event.relation.units:
            hostname = event.relation.data[unit].get("hostname")
            if hostname is not None:
                self._state.hostnames[unit.name] = hostname

    def _on_relation_departed(self, event: RelationDepartedEvent):
        # TODO(neoaggelos): what if the current leader leaves the cluster?
        if not self.unit.is_leader():
            return

        remove_hostname = self._state.hostnames.get(event.departing_unit.name)
        if remove_hostname:
            self._state.remove_nodes.append(remove_hostname)
        self._on_config_changed(None)

    def _check_call(self, *args, **kwargs):
        LOG.debug("Running command %s (%s)", args, kwargs)
        subprocess.check_call(*args, **kwargs)

    def _worker_open_ports(self, _: InstallEvent):
        self.unit.open_port("tcp", 80)
        self.unit.open_port("tcp", 443)

    def _control_plane_open_ports(self, _: InstallEvent):
        self.unit.open_port("tcp", 80)
        self.unit.open_port("tcp", 443)
        self.unit.open_port("tcp", 16443)

    def _on_remove(self, _: RemoveEvent):
        try:
            self._check_call(["snap", "remove", "microk8s", "--purge"])
        except subprocess.CalledProcessError:
            LOG.exception("failed to remove microk8s")

    def _announce_hostname(self, event: Union[RelationJoinedEvent, RelationChangedEvent]):
        event.relation.data[self.unit]["hostname"] = socket.gethostname()

    def _on_install(self, _: InstallEvent):
        if self._state.installed:
            return

        self.unit.status = MaintenanceStatus("installing required packages")
        packages = ["nfs-common", "open-iscsi"]

        try:
            packages.append(f"linux-modules-extra-{os.uname().release}")
        except OSError:
            LOG.exception("could not retrieve kernel version, will not install extra modules")

        for package in packages:
            try:
                self._check_call(["apt-get", "install", "--yes", package])
            except subprocess.CalledProcessError:
                LOG.exception("failed to install package %s, charm may misbehave", package)

        self.unit.status = MaintenanceStatus("installing MicroK8s")
        install_microk8s = ["snap", "install", "microk8s", "--classic"]
        if self.config["channel"]:
            install_microk8s.extend(["--channel", self.config["channel"]])

        self._check_call(install_microk8s)
        try:
            self._check_call(["microk8s", "status", "--wait-ready", "--timeout=30"])
        except subprocess.CalledProcessError:
            LOG.exception("timed out waiting for node to come ups")

        self._state.installed = True
        self._state.joined = False

    def _on_bootstrap_node(self, _: InstallEvent):
        if not self._state.join_url and self.unit.is_leader():
            self._state.joined = True

    def _on_config_changed(self, _: ConfigChangedEvent):
        if self.config["role"] != self._state.role:
            msg = f"role cannot change from '{self._state.role}' after deployment"
            self.unit.status = BlockedStatus(msg)
            return

        if not self._state.installed:
            self._on_install(None)

        if self._state.joined and self.unit.is_leader() and self._state.remove_nodes:
            remove_nodes = list(self._state.remove_nodes)
            self._state.remove_nodes = []
            for hostname in remove_nodes:
                LOG.info("removing node %s", hostname)
                self.unit.status = MaintenanceStatus(f"removing node {hostname}")
                try:
                    self._check_call(["microk8s", "remove-node", hostname, "--force"])
                except subprocess.CalledProcessError:
                    LOG.exception("failed to remove departing node %s", hostname)

        if self._state.joined and self._state.leaving:
            LOG.info("leaving cluster")
            self.unit.status = MaintenanceStatus("leaving cluster")
            self._check_call(["snap", "remove", "microk8s", "--purge"])

            self._state.installed = False
            self._state.joined = False
            self._state.leaving = False
            self._state.join_url = ""

        if not self._state.joined:
            if not self._state.join_url:
                self.unit.status = WaitingStatus("waiting for control plane relation")
                return

            LOG.info("joining cluster")
            self.unit.status = MaintenanceStatus("joining cluster")
            join_cmd = ["microk8s", "join", self._state.join_url]
            if self.config["role"] == "worker":
                join_cmd.append("--worker")
            self._check_call(join_cmd)
            self._state.joined = True

        self.unit.status = util.node_to_unit_status(socket.gethostname())

    def _on_update_status(self, _: UpdateStatusEvent):
        if self._state.joined:
            self.unit.status = util.node_to_unit_status(socket.gethostname())

    def _retrieve_join_url(self, event: Union[RelationChangedEvent, RelationJoinedEvent]):
        # TODO(neoaggelos): corner case where the leader in the control plane peer relation changes
        # before other nodes have time to join. deployment might fail in this case.
        if self._state.joined or (self.config["role"] != "worker" and self.unit.is_leader()):
            return

        join_url = event.relation.data[event.app].get("join_url")
        if not join_url:
            return

        self._state.join_url = join_url
        self._on_config_changed(None)

    def _on_relation_broken(self, _: RelationBrokenEvent):
        self._state.leaving = True
        self._on_config_changed(None)

    def _add_token(self, event: RelationJoinedEvent):
        if not self.unit.is_leader():
            return

        token = os.urandom(16).hex()
        self._check_call(["microk8s", "add-node", "--token", token, "--token-ttl", "7200"])

        event.relation.data[self.app]["join_url"] = "{}:25000/{}".format(
            self.model.get_binding(event.relation).network.ingress_address, token
        )


if __name__ == "__main__":  # pragma: nocover
    main(MicroK8sCharm, use_juju_for_storage=True)
