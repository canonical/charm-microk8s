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
        )

        if self.config["role"] == "worker":
            self.framework.observe(self.on.remove, self._on_remove)
            self.framework.observe(self.on.install, self._on_install)
            self.framework.observe(self.on.install, self._worker_open_ports)
            self.framework.observe(self.on.config_changed, self._on_config_changed)
            self.framework.observe(self.on.update_status, self._on_update_status)
            self.framework.observe(self.on.peer_relation_joined, self._announce_hostname)
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
            self.framework.observe(self.on.peer_relation_joined, self._announce_hostname)
            self.framework.observe(self.on.peer_relation_joined, self._add_token)
            self.framework.observe(self.on.peer_relation_joined, self._retrieve_peer_join_url)
            self.framework.observe(self.on.peer_relation_changed, self._retrieve_peer_join_url)
            self.framework.observe(self.on.microk8s_provides_relation_joined, self._add_token)

    def _worker_open_ports(self, _: InstallEvent):
        self.unit.open_port("tcp", 80)
        self.unit.open_port("tcp", 443)

    def _control_plane_open_ports(self, _: InstallEvent):
        self.unit.open_port("tcp", 80)
        self.unit.open_port("tcp", 443)
        self.unit.open_port("tcp", 16443)

    def _on_remove(self, _: RemoveEvent):
        subprocess.run(["snap", "remove", "microk8s", "--purge"])

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
                subprocess.check_call(["apt-get", "install", "--yes", package])
            except subprocess.CalledProcessError:
                LOG.exception("failed to install package %s, charm may misbehave", package)

        self.unit.status = MaintenanceStatus("installing MicroK8s")
        install_microk8s = ["snap", "install", "microk8s", "--classic"]
        if self.config["channel"]:
            install_microk8s.extend(["--channel", self.config["channel"]])

        subprocess.check_call(install_microk8s)

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

        if self._state.joined and self._state.leaving:
            LOG.info("leaving cluster")
            self.unit.status = MaintenanceStatus("leaving cluster")
            subprocess.check_call(["microk8s", "leave"])

            self._state.joined = False
            self._state.leaving = False
            self._state.join_url = ""

        if not self._state.joined:
            if not self._state.join_url:
                self.unit.status = WaitingStatus("waiting for control plane relation")
                return

            LOG.info("joining cluster")
            self.unit.status = MaintenanceStatus("joining cluster")
            subprocess.check_call(["microk8s", "join", self._state.join_url, "--worker"])
            self._state.joined = True

        self.unit.status = util.node_to_unit_status(socket.gethostname())

    def _on_update_status(self, _: UpdateStatusEvent):
        if self._state.joined:
            self.unit.status = util.node_to_unit_status(socket.gethostname())

    def _retrieve_join_url(self, event: Union[RelationChangedEvent, RelationJoinedEvent]):
        join_url = event.relation.data[event.app].get("join_url")
        if not join_url:
            return

        self._state.join_url = join_url
        self._on_config_changed(None)

    def _retrieve_peer_join_url(self, event: Union[RelationChangedEvent, RelationJoinedEvent]):
        if self._state.joined or self.unit.is_leader():
            return

        self._retrieve_join_url(event)

    def _on_relation_broken(self, _: RelationBrokenEvent):
        self._state.leaving = True
        self._on_config_changed(None)

    def _add_token(self, event: RelationJoinedEvent):
        if not self.unit.is_leader():
            return

        token = os.urandom(16).hex()
        subprocess.check_call(["microk8s", "add-node", "--token", token, "--token-ttl", "7200"])

        event.relation.data[self.app]["join_url"] = "{}:25000/{}".format(
            self.model.get_binding(event.relation).network.ingress_address, token
        )


if __name__ == "__main__":  # pragma: nocover
    main(MicroK8sCharm, use_juju_for_storage=True)
