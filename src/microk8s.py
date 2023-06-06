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

import charm_config
import util

LOG = logging.getLogger(__name__)


def snap_dir() -> Path:
    return Path("/snap/microk8s/current")


def snap_data_dir() -> Path:
    return Path("/var/snap/microk8s/current")


def snap_common_dir() -> Path:
    return Path("")


def install():
    """`snap install microk8s`"""
    LOG.info("Installing MicroK8s (channel %s)", charm_config.SNAP_CHANNEL)
    cmd = ["snap", "install", "microk8s", "--classic", "--channel", charm_config.SNAP_CHANNEL]

    util.check_call(cmd)


def upgrade():
    """upgrade microk8s to charm version"""
    LOG.info("Upgrade MicroK8s (channel %s)", charm_config.SNAP_CHANNEL)
    cmd = ["snap", "refresh", "microk8s", "--channel", charm_config.SNAP_CHANNEL]

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
