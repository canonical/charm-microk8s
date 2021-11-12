from collections import namedtuple
from unittest import TestCase
from unittest.mock import patch

from ops.testing import Harness

from charm import MicroK8sCharm

MockEvent = namedtuple("MockEvent", ["unit", "relation"])
MockUnit = namedtuple("MockUnit", ["name"])
MockData = namedtuple("MockData", ["data"])


class TestHostnameManager(TestCase):
    def setUp(self):
        self.harness = Harness(MicroK8sCharm)
        self.harness.begin()

        unit = MockUnit(name="microk8s/10")
        event = MockEvent(unit=unit, relation=MockData(data={unit: {"hostname": "myhostname"}}))
        self.event = event

    def test_remember_empty(self):
        self.harness.charm.cluster.hostnames._remember_hostname(MockEvent(unit=None, relation=None))
        self.assertEqual(self.harness.charm.cluster.hostnames.peers, {})

    def test_remember(self):
        self.harness.charm.cluster.hostnames._remember_hostname(self.event)
        self.assertEqual(self.harness.charm.cluster.hostnames.all_peers, {"microk8s/10": "myhostname"})
        self.assertEqual(self.harness.charm.cluster.hostnames.peers, {"microk8s/10": "myhostname"})

    def test_forget(self):
        self.harness.charm.cluster.hostnames._remember_hostname(self.event)
        self.assertEqual(self.harness.charm.cluster.hostnames.peers, {"microk8s/10": "myhostname"})

        with patch("os.environ.get") as _get:
            _get.return_value = "microk8s/10"
            self.harness.charm.cluster.hostnames._forget_hostname(None)

        self.assertEqual(self.harness.charm.cluster.hostnames.all_peers, {"microk8s/10": "myhostname"})
        self.assertEqual(self.harness.charm.cluster.hostnames.peers, {})
