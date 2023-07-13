#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import config
import pytest
from pytest_operator.plugin import OpsTest


@pytest.mark.abort_on_fail
async def test_observability_metrics(e: OpsTest):
    await e.model.deploy(
        config.MK8S_CHARM,
        application_name="microk8s",
        channel=config.MK8S_CHARM_CHANNEL,
        constraints=config.MK8S_CONSTRAINTS,
    )
    await e.model.wait_for_idle(["microk8s"])

    await e.model.deploy(
        config.MK8S_GRAFANA_AGENT_CHARM,
        channel=config.MK8S_GRAFANA_AGENT_CHANNEL,
        application_name="grafana-agent",
    )
    await e.model.relate("microk8s", "grafana-agent")

    # TODO(neoaggelos): enable tests after required issues are fixed
    # - https://github.com/simskij/grafana-agent/issues/22
    # - https://github.com/canonical/grafana-agent-k8s-operator/issues/190
    # - https://github.com/canonical/grafana-agent-k8s-operator/pull/223
    # - https://github.com/canonical/grafana-agent-k8s-operator/pull/222
    # - https://github.com/canonical/grafana-agent-k8s-operator/pull/220
    # - https://github.com/canonical/grafana-agent-k8s-operator/pull/219
    # await e.model.wait_for_idle(["microk8s", "grafana-agent"])

    # For now, just ensure that microk8s does not fail
    await e.model.wait_for_idle(["microk8s"])
