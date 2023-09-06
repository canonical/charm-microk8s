#
# Copyright 2023 Canonical, Ltd.
#
from dataclasses import dataclass
from unittest import mock

import ops.testing
import pytest
from ops.model import ActiveStatus

from charm import MicroK8sCharm


@dataclass
class Environment:
    """Environment is an environment for testing the charm"""

    harness: ops.testing.Harness

    # standard library mocks
    gethostname: mock.MagicMock
    sleep: mock.MagicMock

    # project mocks
    containerd: mock.MagicMock
    COSAgentProvider: mock.MagicMock
    metrics: mock.MagicMock
    microk8s: mock.MagicMock
    util: mock.MagicMock


@pytest.fixture
def e():
    harness = ops.testing.Harness(MicroK8sCharm)
    patchers = {
        # standard library mocks
        "gethostname": mock.patch("socket.gethostname", autospec=True),
        "sleep": mock.patch("time.sleep", autospec=True),
        # project mocks
        "containerd": mock.patch("charm.containerd", autospec=True),
        "COSAgentProvider": mock.patch("charm.COSAgentProvider", autospec=True),
        "metrics": mock.patch("charm.metrics", autospec=True),
        "microk8s": mock.patch("charm.microk8s", autospec=True),
        "util": mock.patch("charm.util", autospec=True),
    }

    mocks = {}
    for k, v in patchers.items():
        mocks[k] = v.start()

    e = Environment(harness, **mocks)

    # default mocks
    e.microk8s.get_kubernetes_version.return_value = "fakeversion"
    e.microk8s.get_unit_status.return_value = ActiveStatus("fakestatus")
    e.gethostname.return_value = "fakehostname"

    yield e

    harness.cleanup()
    for k, v in patchers.items():
        v.stop()
