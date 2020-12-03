# Copyright 2020 Paul Collins
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops.model import ActiveStatus
from ops.testing import Harness
from charm import MicroK8sCharm
from microk8scluster import DEFAULT_ADDONS


class TestCharm(unittest.TestCase):
    @patch("subprocess.check_call")
    def test_begin_with_initial_hooks(self, _check_call):
        harness = Harness(MicroK8sCharm)
        self.addCleanup(harness.cleanup)

        # Assert we have DEFAULT_ADDONS so we know they should be enabled.
        self.assertEqual(DEFAULT_ADDONS, ["dns", "ingress"])
        harness.begin_with_initial_hooks()
        expected_subprocess_calls = [
            ['/usr/bin/snap', 'install', '--classic', 'microk8s'],
            ['/snap/bin/microk8s', 'enable', 'dns', 'ingress'],
        ]
        self.assertEqual(_check_call.call_args_list, [unittest.mock.call(x) for x in expected_subprocess_calls])
        self.assertEqual(harness.charm.unit.status, ActiveStatus())
