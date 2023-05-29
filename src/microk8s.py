#
# Copyright 2023 Canonical, Ltd.
#
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus

import util

LOG = logging.getLogger(__name__)


SNAP = Path("/snap/microk8s/current")
SNAP_DATA = Path("/var/snap/microk8s/current")
SNAP_COMMON = Path("/var/snap/microk8s/common")


def install(channel: Optional[str] = None):
    """`snap install microk8s`"""
    LOG.info("Installing MicroK8s (channel %s)", channel)
    cmd = ["snap", "install", "microk8s", "--classic"]
    if channel:
        cmd.extend(["--channel", channel])

    util.check_call(cmd)


def wait_ready(timeout: int = 30):
    """`microk8s status --wait-ready`"""
    LOG.info("Wait for MicroK8s to become ready")
    util.check_call(["microk8s", "status", "--wait-ready", f"--timeout={timeout}"])


def uninstall():
    """`snap remove microk8s --purge`"""
    LOG.info("Uninstall MicroK8s")
    util.check_call(["snap", "remove", "microk8s", "--purge"])


def remove_node(hostname: str):
    """`microk8s remove-node --force`"""
    LOG.info("Removing node %s from cluster", hostname)
    util.check_call(["microk8s", "remove-node", hostname, "--force"])


def join(join_url: str, worker: bool):
    """`microk8s join`"""
    LOG.info("Joining cluster")
    cmd = ["microk8s", "join", join_url]
    if worker:
        cmd.append("--worker")

    util.check_call(cmd)


def add_node() -> str:
    """`microk8s add-node` and return join token"""
    LOG.info("Generating token for new node")
    token = os.urandom(16).hex()
    util.check_call(["microk8s", "add-node", "--token", token, "--token-ttl", "7200"])
    return token


def get_unit_status(hostname: str):
    """Retrieve node Ready condition from Kubernetes and convert to Juju unit status."""
    try:
        # use the kubectl binary with the kubelet config directly
        output = subprocess.check_output(
            [
                f"{SNAP}/kubectl",
                f"--kubeconfig={SNAP_DATA}/credentials/kubelet.config",
                "get",
                "node",
                hostname,
                "-o",
                "jsonpath={.status.conditions[?(@.type=='Ready')]}",
            ]
        )
        node_ready_condition = json.loads(output)
        if node_ready_condition["status"] == "False":
            LOG.warning("node %s is not ready: %s", hostname, node_ready_condition)
            return WaitingStatus(f"node is not ready: {node_ready_condition['reason']}")

        return ActiveStatus("node is ready")

    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
        LOG.warning("could not retrieve status of node %s: %s", hostname, e)
        return MaintenanceStatus("waiting for node")


def reconcile_addons(enabled_addons: list, target_addons: list):
    """disable removed and enable missing addons"""
    LOG.info("Reconciling addons (current=%s, wanted=%s)", enabled_addons, target_addons)
    for addon in enabled_addons:
        if addon not in target_addons:
            # drop any arguments from the addon (if any)
            # e.g. 'dns:10.0.0.10' -> 'dns'
            addon_name, *_ = addon.split(":", maxsplit=2)
            LOG.info("Disabling addon %s", addon_name)
            util.check_call(["microk8s", "disable", addon_name])

    for addon in target_addons:
        if addon not in enabled_addons:
            LOG.info("Enabling addon %s", addon)
            util.check_call(["microk8s", "enable", addon])
