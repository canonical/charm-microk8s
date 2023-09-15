#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import config
import pytest
from pytest_operator.plugin import OpsTest


@pytest.mark.abort_on_fail
async def test_observability_metrics(e: OpsTest, charm_config: dict):
    await e.model.deploy(
        config.MK8S_CHARM,
        application_name="microk8s",
        channel=config.MK8S_CHARM_CHANNEL,
        constraints=config.MK8S_CONSTRAINTS,
        config=charm_config,
    )
    await e.model.wait_for_idle(["microk8s"])

    await e.model.deploy(
        config.MK8S_GRAFANA_AGENT_CHARM,
        channel=config.MK8S_GRAFANA_AGENT_CHANNEL,
        application_name="grafana-agent",
    )
    await e.model.relate("microk8s", "grafana-agent")

    await e.model.wait_for_idle(["microk8s"])

    # TODO: add tests that grafana-agent picks up the required jobs
