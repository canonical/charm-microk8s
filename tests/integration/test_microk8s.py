#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import config
import pytest
from conftest import run_unit
from juju.unit import Unit
from pytest_operator.plugin import OpsTest


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("cp_units, worker_units", config.MK8S_CLUSTER_SIZES)
@pytest.mark.parametrize("series", config.MK8S_SERIES)
async def test_microk8s_cluster(e: OpsTest, series: str, cp_units: int, worker_units: int):
    """Deploy a cluster, configure RBAC, wait for units to come up"""

    charm_config = {}
    application_name = f"microk8s-{series or 'default'}-{cp_units}c{worker_units}w"

    apps = []
    apps.append(
        await e.model.deploy(
            config.MK8S_CHARM,
            application_name=application_name,
            num_units=cp_units,
            config=charm_config,
            channel=config.MK8S_CHARM_CHANNEL,
            revision=config.MK8S_CHARM_REVISION,
            series=series,
            constraints=config.MK8S_CONSTRAINTS,
        )
    )

    await e.model.wait_for_idle([application_name], timeout=60 * 60)

    u: Unit = e.model.applications[application_name].units[0]

    # When rbac is not enabled, we can't query for `system:node` cluster role
    rc, stdout, stderr = await run_unit(u, "microk8s kubectl get clusterrole system:node")
    assert rc == 1, f"system:node should be missing with RBAC disabled {stdout=}, {stderr=}"

    await e.model.wait_for_idle([application_name], timeout=60 * 60)

    # When rbac is enabled via configs, we can get `system:node` clusterrole successfully
    await e.model.applications[application_name].set_config(
        config={"rbac": "true"},
    )

    await e.model.wait_for_idle([application_name], timeout=60 * 60)

    if worker_units > 0:
        apps.append(
            await e.model.deploy(
                config.MK8S_CHARM,
                application_name=f"{application_name}-worker",
                num_units=worker_units,
                config={"role": "worker", **charm_config},
                channel=config.MK8S_CHARM_CHANNEL,
                revision=config.MK8S_CHARM_REVISION,
                series=series,
                constraints=config.MK8S_CONSTRAINTS,
            )
        )

        await e.model.add_relation(
            f"{application_name}:workers", f"{application_name}-worker:control-plane"
        )

        await e.model.wait_for_idle([f"{application_name}-worker"], timeout=60 * 60)

    await e.model.wait_for_idle([application_name], timeout=60 * 60)

    # When rbac is enabled, we can get `system:node` clusterrole successfully
    rc, stdout, stderr = await run_unit(u, "microk8s kubectl get clusterrole system:node")
    assert rc == 0, f"system:node should be present with RBAC enabled {stdout=} {stderr=}"

    await e.model.wait_for_idle([a.name for a in apps], timeout=60 * 60)
    for a in apps:
        await e.model.remove_application(a.name, block_until_done=True)
