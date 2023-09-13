#
# Copyright 2023 Canonical, Ltd.
#
import pytest
from conftest import Environment
from ops.model import BlockedStatus


@pytest.mark.parametrize("role", ["", "control-plane"])
def test_regression_charm_remains_blocked_on_invalid_containerd_registries_config_after_join(
    e: Environment, role: str
):
    e.containerd.parse_registries.side_effect = ValueError("mock invalid registry configs")

    e.harness.update_config({"role": role})
    e.harness.set_leader(False)
    e.harness.begin_with_initial_hooks()
    assert isinstance(e.harness.charm.unit.status, BlockedStatus)

    prel_id = e.harness.charm.model.get_relation("peer").id
    e.harness.update_relation_data(prel_id, e.harness.charm.app.name, {"join_url": "join"})

    assert e.harness.charm._state.joined
    assert isinstance(e.harness.charm.unit.status, BlockedStatus)
