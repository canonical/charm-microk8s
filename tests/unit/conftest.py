#
# Copyright 2023 Canonical, Ltd.
#
from dataclasses import dataclass
from unittest import mock

import ops.testing
import pytest

from charm import MicroK8sCharm


@dataclass
class Environment:
    """Environment is an environment for testing the charm"""

    harness: ops.testing.Harness

    # mocks
    check_call: mock.MagicMock
    get_hostname: mock.MagicMock
    node_to_unit_status: mock.MagicMock
    run: mock.MagicMock
    uname: mock.MagicMock
    urandom: mock.MagicMock


@pytest.fixture
def e():
    harness = ops.testing.Harness(MicroK8sCharm)
    patchers = {
        "check_call": mock.patch("subprocess.check_call"),
        "get_hostname": mock.patch("socket.gethostname"),
        "node_to_unit_status": mock.patch("util.node_to_unit_status"),
        "run": mock.patch("subprocess.run"),
        "uname": mock.patch("os.uname"),
        "urandom": mock.patch("os.urandom"),
    }

    mocks = {}
    for k, v in patchers.items():
        mocks[k] = v.start()

    yield Environment(harness, **mocks)

    harness.cleanup()
    for k, v in patchers.items():
        v.stop()
