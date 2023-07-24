#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import json
import logging
import socket
import subprocess
import time
from typing import Any, Union

from charms.grafana_agent.v0.cos_agent import COSAgentProvider
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
    UpgradeCharmEvent,
)
from ops.framework import StoredState
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

import containerd
import metrics
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
            hostnames={},
        )

        if self.config["role"] == "worker":
            # lifecycle
            self.framework.observe(self.on.remove, self.on_remove)
            self.framework.observe(self.on.upgrade_charm, self.on_upgrade)
            self.framework.observe(self.on.install, self.on_install)
            self.framework.observe(self.on.update_status, self.update_status)

            # configuration
            self.framework.observe(self.on.config_changed, self.config_ensure_role)
            self.framework.observe(self.on.config_changed, self.on_install)
            self.framework.observe(self.on.config_changed, self.config_containerd_proxy)
            self.framework.observe(self.on.config_changed, self.config_containerd_registries)
            self.framework.observe(self.on.config_changed, self.update_status)

            # clustering
            self.framework.observe(self.on.control_plane_relation_joined, self.on_install)
            self.framework.observe(self.on.control_plane_relation_joined, self.announce_hostname)
            self.framework.observe(self.on.control_plane_relation_changed, self.join_cluster)
            self.framework.observe(self.on.control_plane_relation_changed, self.update_status)
            self.framework.observe(self.on.control_plane_relation_broken, self.leave_cluster)
            self.framework.observe(self.on.control_plane_relation_broken, self.update_status)
        else:
            # lifecycle
            self.framework.observe(self.on.remove, self.on_remove)
            self.framework.observe(self.on.upgrade_charm, self.on_upgrade)
            self.framework.observe(self.on.install, self.on_install)
            self.framework.observe(self.on.install, self.bootstrap_cluster)
            self.framework.observe(self.on.install, self.open_ports)
            self.framework.observe(self.on.leader_elected, self.remove_departed_nodes)
            self.framework.observe(self.on.leader_elected, self.update_status)
            self.framework.observe(self.on.update_status, self.update_status)
            self.framework.observe(self.on.update_status, self.update_scrape_token)

            # configuration
            self.framework.observe(self.on.config_changed, self.config_ensure_role)
            self.framework.observe(self.on.config_changed, self.on_install)
            self.framework.observe(self.on.config_changed, self.config_containerd_proxy)
            self.framework.observe(self.on.config_changed, self.config_containerd_registries)
            self.framework.observe(self.on.config_changed, self.config_hostpath_storage)
            self.framework.observe(self.on.config_changed, self.config_certificate_reissue)
            self.framework.observe(self.on.config_changed, self.config_extra_sans)
            self.framework.observe(self.on.config_changed, self.config_rbac)
            self.framework.observe(self.on.config_changed, self.update_status)

            # clustering
            self.framework.observe(self.on.peer_relation_joined, self.add_node)
            self.framework.observe(self.on.peer_relation_joined, self.announce_hostname)
            self.framework.observe(self.on.peer_relation_joined, self.record_hostnames)
            self.framework.observe(self.on.peer_relation_joined, self.join_cluster)
            self.framework.observe(self.on.peer_relation_joined, self.config_extra_sans)
            self.framework.observe(self.on.peer_relation_joined, self.update_status)
            self.framework.observe(self.on.peer_relation_changed, self.record_hostnames)
            self.framework.observe(self.on.peer_relation_changed, self.join_cluster)
            self.framework.observe(self.on.peer_relation_changed, self.config_extra_sans)
            self.framework.observe(self.on.peer_relation_changed, self.update_status)
            self.framework.observe(self.on.peer_relation_departed, self.on_relation_departed)
            self.framework.observe(self.on.peer_relation_departed, self.remove_departed_nodes)
            self.framework.observe(self.on.peer_relation_departed, self.update_status)
            self.framework.observe(self.on.workers_relation_joined, self.add_node)
            self.framework.observe(self.on.workers_relation_joined, self.update_scrape_token)
            self.framework.observe(self.on.workers_relation_changed, self.record_hostnames)
            self.framework.observe(self.on.workers_relation_departed, self.on_relation_departed)
            self.framework.observe(self.on.workers_relation_departed, self.remove_departed_nodes)
            self.framework.observe(self.on.workers_relation_departed, self.update_status)

            # observability
            self.framework.observe(
                self.on.cos_agent_relation_joined, self.apply_observability_resources
            )
            self.framework.observe(self.on.cos_agent_relation_joined, self.update_scrape_token)
            self._cos = COSAgentProvider(
                self,
                relation_name="cos-agent",
                scrape_configs=self._build_scrape_configs,
                metrics_rules_dir="src/prometheus_alert_rules",
                dashboard_dirs=["src/grafana_dashboards"],
                refresh_events=[self.on.peer_relation_changed, self.on.upgrade_charm],
            )

    def on_remove(self, _: RemoveEvent):
        try:
            microk8s.uninstall()
        except subprocess.CalledProcessError:
            LOG.exception("failed to remove microk8s")

    def on_upgrade(self, _: UpgradeCharmEvent):
        # TODO(neoaggelos): Figure out an orchestrated upgrade strategy
        microk8s.upgrade()

    def on_install(self, _: InstallEvent):
        if self._state.installed:
            return

        self.unit.status = MaintenanceStatus("installing required packages")
        util.install_required_packages()

        self.unit.status = MaintenanceStatus("installing MicroK8s")
        microk8s.install()
        try:
            microk8s.wait_ready()
        except subprocess.CalledProcessError:
            LOG.exception("timed out waiting for node to come up")

        self._state.installed = True
        self._state.joined = False

    def config_ensure_role(self, _: ConfigChangedEvent):
        if self.config["role"] != self._state.role:
            msg = f"role cannot change from '{self._state.role}' after deployment"
            self.unit.status = BlockedStatus(msg)
        else:
            self.unit.status = MaintenanceStatus("maintenance")

    def config_containerd_proxy(self, _: ConfigChangedEvent):
        if isinstance(self.unit.status, BlockedStatus):
            return

        microk8s.set_containerd_proxy_options(
            self.config["containerd_http_proxy"],
            self.config["containerd_https_proxy"],
            self.config["containerd_no_proxy"],
        )

    def config_containerd_registries(self, _: ConfigChangedEvent):
        if isinstance(self.unit.status, BlockedStatus):
            return

        try:
            registries = containerd.parse_registries(self.config["containerd_custom_registries"])
            if registries:
                self.unit.status = MaintenanceStatus("configure containerd registries")
                containerd.ensure_registry_configs(registries)
        except (ValueError, subprocess.CalledProcessError, OSError):
            LOG.exception("failed to configure containerd registries")
            self.unit.status = BlockedStatus(
                "failed to apply containerd_custom_registries, check logs for details"
            )

    def config_rbac(self, _: ConfigChangedEvent):
        if isinstance(self.unit.status, BlockedStatus):
            return

        if self._state.joined:
            self.unit.status = MaintenanceStatus("configuring RBAC")
            microk8s.wait_ready()
            microk8s.configure_rbac(self.config["rbac"])

    def config_hostpath_storage(self, _: ConfigChangedEvent):
        if isinstance(self.unit.status, BlockedStatus):
            return

        if self._state.joined and self.unit.is_leader():
            microk8s.configure_hostpath_storage(self.config["hostpath_storage"])

    def config_certificate_reissue(self, _: ConfigChangedEvent):
        if isinstance(self.unit.status, BlockedStatus):
            return

        if self._state.joined and not self.config["automatic_certificate_reissue"]:
            self.unit.status = MaintenanceStatus("disabling automatic certificate reissue")
            microk8s.wait_ready()
            microk8s.disable_cert_reissue()

    def config_extra_sans(self, _: ConfigChangedEvent):
        if isinstance(self.unit.status, BlockedStatus):
            return

        if self._state.joined:
            self.unit.status = MaintenanceStatus("configuring extra SANs")
            microk8s.configure_extra_sans(self.config["extra_sans"])

    def update_status(self, _: Union[UpdateStatusEvent, ConfigChangedEvent]):
        if isinstance(self.unit.status, BlockedStatus):
            return

        if not self._state.joined:
            self.unit.status = WaitingStatus("waiting for control plane")
            return

        self.unit.status = microk8s.get_unit_status(socket.gethostname())
        while not isinstance(self.unit.status, ActiveStatus):
            time.sleep(2)
            self.unit.status = microk8s.get_unit_status(socket.gethostname())

    def record_hostnames(self, event: Union[RelationChangedEvent, RelationJoinedEvent]):
        for unit in event.relation.units:
            hostname = event.relation.data[unit].get("hostname")
            if hostname is not None:
                self._state.hostnames[unit.name] = hostname

    def on_relation_departed(self, event: RelationDepartedEvent):
        if event.departing_unit == self.unit:
            self._state.joined = False

        remove_hostname = self._state.hostnames.pop(event.departing_unit.name, None)
        if not self.unit.is_leader():
            return

        if remove_hostname:
            remove_nodes = self._get_peer_data("remove_nodes", [])
            remove_nodes.append(remove_hostname)
            self._set_peer_data("remove_nodes", remove_nodes)

    def remove_departed_nodes(self, _: Union[RelationDepartedEvent, LeaderElectedEvent]):
        if self._state.joined and self.unit.is_leader():
            remove_nodes = self._get_peer_data("remove_nodes", [])

            new_remove_nodes = []
            for hostname in set(remove_nodes):
                # skip self, someone else will remove us when they become leader
                if hostname == socket.gethostname():
                    new_remove_nodes.append(hostname)
                    continue

                self.unit.status = MaintenanceStatus(f"removing node {hostname}")
                try:
                    microk8s.remove_node(hostname)
                except subprocess.CalledProcessError:
                    new_remove_nodes.append(hostname)
                    LOG.exception("failed to remove departing node %s", hostname)

            self._set_peer_data("remove_nodes", new_remove_nodes)

    def open_ports(self, _: InstallEvent):
        self.unit.open_port("tcp", 16443)

    def announce_hostname(self, event: Union[RelationJoinedEvent, RelationChangedEvent]):
        hostname = socket.gethostname()
        self._state.hostnames[self.unit.name] = hostname
        event.relation.data[self.unit]["hostname"] = hostname

    def bootstrap_cluster(self, _: InstallEvent):
        # FIXME(neoaggelos): possible race condition if leadership changes during bootstrap
        if self.unit.is_leader():
            self._state.joined = True

    def join_cluster(self, event: Union[RelationJoinedEvent, RelationChangedEvent]):
        if self._state.joined or (self.config["role"] != "worker" and self.unit.is_leader()):
            return

        join_url = event.relation.data[event.app].get("join_url")
        if not join_url:
            LOG.info("join URL not yet available")
            return

        self.unit.status = MaintenanceStatus("joining cluster")
        microk8s.join(join_url, self.config["role"] == "worker")
        microk8s.wait_ready()
        self._state.joined = True

    def leave_cluster(self, _: RelationBrokenEvent):
        if not self._state.joined:
            return

        LOG.info("leaving cluster")
        self.unit.status = MaintenanceStatus("leaving cluster")
        microk8s.uninstall()

        self._state.installed = False
        self._state.joined = False

    def add_node(self, event: RelationJoinedEvent):
        if not self.unit.is_leader():
            return

        token = microk8s.add_node()
        event.relation.data[self.app]["join_url"] = "{}:25000/{}".format(
            self.model.get_binding(event.relation).network.ingress_address, token
        )

    def apply_observability_resources(self, _: RelationJoinedEvent):
        if isinstance(self.unit.status, BlockedStatus):
            return

        if self._state.joined and self.unit.is_leader():
            metrics.apply_required_resources()

    def update_scrape_token(self, _: Any):
        if not self.unit.is_leader() or not self.model.relations["cos-agent"]:
            return

        try:
            token = metrics.get_bearer_token()
        except subprocess.CalledProcessError:
            LOG.exception("failed to retrieve authentication token for observability")
            return

        for relation in self.model.relations["peer"]:
            relation.data[self.app]["metrics_token"] = token
        for relation in self.model.relations["workers"]:
            relation.data[self.app]["metrics_token"] = token

    def _build_scrape_configs(self) -> list:
        if not self._state.joined:
            return []

        is_control_plane = self.config["role"] != "worker"
        control_relation_name = "peer" if is_control_plane else "control-plane"
        relation = self.model.get_relation(control_relation_name)

        try:
            token = relation.data[relation.app]["metrics_token"]
        except (KeyError, AttributeError):
            LOG.debug("metrics token not yet available")
            return []

        return metrics.build_scrape_jobs(token, is_control_plane, socket.gethostname())


if __name__ == "__main__":  # pragma: nocover
    main(MicroK8sCharm, use_juju_for_storage=True)
