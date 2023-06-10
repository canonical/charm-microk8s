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

    # standard library mocks
    gethostname: mock.MagicMock

    # project mocks
    containerd: mock.MagicMock
    microk8s: mock.MagicMock
    util: mock.MagicMock


@pytest.fixture
def e():
    harness = ops.testing.Harness(MicroK8sCharm)
    patchers = {
        # standard library mocks
        "gethostname": mock.patch("socket.gethostname", autospec=True),
        # project mocks
        "containerd": mock.patch("charm.containerd", autospec=True),
        "microk8s": mock.patch("charm.microk8s", autospec=True),
        "util": mock.patch("charm.util", autospec=True),
    }

    mocks = {}
    for k, v in patchers.items():
        mocks[k] = v.start()

    yield Environment(harness, **mocks)

    harness.cleanup()
    for k, v in patchers.items():
        v.stop()
