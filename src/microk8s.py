#
# Copyright 2023 Canonical, Ltd.
#
import ipaddress
import json
import logging
import os
import shlex
import subprocess
from pathlib import Path

from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus

import charm_config
import ops_helpers
import util

LOG = logging.getLogger(__name__)


def snap_dir() -> Path:
    return Path("/snap/microk8s/current")


def snap_data_dir() -> Path:
    return Path("/var/snap/microk8s/current")


def install():
    """`snap install microk8s`"""
    LOG.info("Installing MicroK8s (channel %s)", charm_config.SNAP_CHANNEL)
    cmd = ["snap", "install", "microk8s", "--classic", "--channel", charm_config.SNAP_CHANNEL]

    util.ensure_call(cmd)


def upgrade():
    """upgrade microk8s to charm version"""
    LOG.info("Upgrade MicroK8s (channel %s)", charm_config.SNAP_CHANNEL or "default")
    cmd = ["snap", "refresh", "microk8s", "--channel", charm_config.SNAP_CHANNEL]

    util.ensure_call(cmd)


def wait_ready(timeout: int = 30):
    """`microk8s status --wait-ready`"""
    LOG.info("Wait for MicroK8s to become ready")
    util.ensure_call(["microk8s", "status", "--wait-ready", f"--timeout={timeout}"])


def uninstall():
    """`snap remove microk8s --purge`"""
    LOG.info("Uninstall MicroK8s")
    util.ensure_call(["snap", "remove", "microk8s", "--purge"])


def remove_node(hostname: str):
    """`microk8s remove-node --force`"""
    LOG.info("Removing node %s from cluster", hostname)
    util.ensure_call(["microk8s", "remove-node", hostname, "--force"])


def join(join_url: str, worker: bool):
    """`microk8s join`"""
    LOG.info("Joining cluster")
    cmd = ["microk8s", "join", join_url]
    if worker:
        cmd.append("--worker")

    util.ensure_call(cmd)


def add_node() -> str:
    """`microk8s add-node` and return join token"""
    LOG.info("Generating token for new node")
    token = os.urandom(16).hex()
    util.ensure_call(["microk8s", "add-node", "--token", token, "--token-ttl", "7200"])
    return token


def get_unit_status(hostname: str):
    """Retrieve node Ready condition from Kubernetes and convert to Juju unit status."""
    try:
        # use the kubectl binary with the kubelet config directly
        output = subprocess.check_output(
            [
                f"{snap_dir()}/kubectl",
                f"--kubeconfig={snap_data_dir()}/credentials/kubelet.config",
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


def set_containerd_proxy_options(http_proxy: str, https_proxy: str, no_proxy: str):
    """update containerd http proxy configuration and restart containerd if changed"""

    proxy_config = []
    if http_proxy:
        proxy_config.append(f"http_proxy={shlex.quote(http_proxy)}")
    if https_proxy:
        proxy_config.append(f"https_proxy={shlex.quote(https_proxy)}")
    if no_proxy:
        proxy_config.append(f"no_proxy={shlex.quote(no_proxy)}")

    if not proxy_config:
        LOG.debug("No containerd proxy configuration specified")
        return

    LOG.info("Set containerd http proxy configuration %s", proxy_config)

    path = snap_data_dir() / "args" / "containerd-env"
    containerd_env = path.read_text() if path.exists() else ""
    new_containerd_env = util.ensure_block(
        containerd_env, "\n".join(proxy_config), "{mark} managed by microk8s charm"
    )

    if util.ensure_file(path, new_containerd_env, 0o600, 0, 0):
        LOG.info("Restart containerd to apply environment configuration")
        util.ensure_call(["snap", "restart", "microk8s.daemon-containerd"])


def disable_cert_reissue():
    """disable automatic cert reissue. this must never be done on nodes that have not yet joined"""
    LOG.info("Disable automatic certificate reissue")

    path = snap_data_dir() / "var" / "lock" / "no-cert-reissue"
    if not path.exists():
        util.ensure_file(path, "", 0o600, 0, 0)


def configure_extra_sans(extra_sans_str: str):
    """add a list of extra SANs that are accepted by the kube-apiserver"""

    if not extra_sans_str:
        LOG.debug("No extra SANs will be configured")
        return

    if "%UNIT_PUBLIC_ADDRESS%" in extra_sans_str:
        extra_sans_str = extra_sans_str.replace(
            "%UNIT_PUBLIC_ADDRESS%", ops_helpers.get_unit_public_address()
        )

    extra_sans = extra_sans_str.split(",")

    entries = ["[ alt_names ]"]
    for idx, san in enumerate(extra_sans):
        prefix = "IP"
        try:
            ipaddress.ip_address(san)
        except ValueError:
            prefix = "DNS"

        entries.append(f"{prefix}.{idx + 1000} = {san}")

    path = snap_data_dir() / "certs" / "csr.conf.template"
    csr_conf = path.read_text() if path.exists() else ""
    new_csr_conf = util.ensure_block(
        csr_conf, "\n".join(entries), "# {mark} managed by microk8s charm"
    )

    if util.ensure_file(path, new_csr_conf, 0o600, 0, 0):
        LOG.info("Update kube-apiserver certificate with extra SANs %s", extra_sans)
        util.ensure_call(["microk8s", "refresh-certs", "-e", "server.crt"])
