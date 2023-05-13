#
# Copyright 2023 Canonical, Ltd.
#
import json
import logging
import subprocess

from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus

LOG = logging.getLogger(__name__)


def node_to_unit_status(hostname: str):
    """Retrieve Kubernetes node status and convert to Juju unit status."""
    try:
        ready_condition = _unsafe_kubernetes_get_node_ready_condition(hostname)
        if ready_condition["status"] == "False":
            LOG.warning("node %s is not ready: %s", hostname, ready_condition)
            return WaitingStatus(f"node is not ready: {ready_condition['reason']}")

        return ActiveStatus("node is ready")

    except (OSError, json.JSONDecodeError) as e:
        LOG.exception("could not retrieve status of node %s: %s", hostname, e)
        return MaintenanceStatus("waiting for node")


def _unsafe_kubernetes_get_node_ready_condition(hostname: str):
    """Return a JSON object describing the Kubernetes node status of type Ready."""
    # worker nodes cannot use 'microk8s kubectl', invoke kubectl directly with the kubelet config
    output = subprocess.check_output(
        [
            "/snap/microk8s/current/kubectl",
            "--kubeconfig=/var/snap/microk8s/current/credentials/kubelet.config",
            "get",
            "node",
            hostname,
            "-o",
            "jsonpath={.status.conditions[?(@.type=='Ready')]}",
        ]
    )
    return json.loads(output)
