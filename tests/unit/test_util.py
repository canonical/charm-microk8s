#
# Copyright 2023 Canonical, Ltd.
#
from unittest import mock

import pytest
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus

import util

STATUS_MESSAGES = {
    "NOT_READY_STATUS": """
{
    "lastHeartbeatTime": "2023-05-12T05:54:05Z",
    "lastTransitionTime": "2023-05-12T05:54:05Z",
    "message": "[container runtime network not ready: NetworkReady=false reason:NetworkPluginNotReady message:Network plugin returns error: cni plugin not initialized, CSINode is not yet initialized]",
    "reason": "KubeletNotReady",
    "status": "False",
    "type": "Ready"
}
""",  # noqa
    "READY_STATUS": """
{
    "lastHeartbeatTime": "2023-05-12T05:54:22Z",
    "lastTransitionTime": "2023-05-12T05:54:22Z",
    "message": "kubelet is posting ready status. AppArmor enabled",
    "reason": "KubeletReady",
    "status": "True",
    "type": "Ready"
}
""",
    "INVALID_STATUS": """not a json message""",
}


@mock.patch("subprocess.check_call")
@pytest.mark.parametrize(
    "message, expect_status",
    [
        ("READY_STATUS", ActiveStatus("node is ready")),
        ("NOT_READY_STATUS", WaitingStatus("node is not ready: KubeletNotReady")),
        ("INVALID_STATUS", MaintenanceStatus("waiting for node")),
    ],
)
def test_node_to_unit_status(_check_call, message, expect_status):
    _check_call.return_value = STATUS_MESSAGES[message].encode()

    assert util.node_to_unit_status("fakehostname") == expect_status
