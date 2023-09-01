#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import asyncio
import logging

import config
import pytest
from conftest import microk8s_kubernetes_cloud_and_model, run_unit
from pytest_operator.plugin import OpsTest

LOG = logging.getLogger(__name__)


@pytest.fixture()
async def microk8s(e: OpsTest):
    # deploy microk8s
    if "microk8s" not in e.model.applications:
        await e.model.deploy(
            config.MK8S_CHARM,
            application_name="microk8s",
            config={"hostpath_storage": "true"},
            channel=config.MK8S_CHARM_CHANNEL,
            constraints=config.MK8S_CONSTRAINTS,
        )
        await e.model.wait_for_idle(["microk8s"])

    yield e.model.applications["microk8s"]


@pytest.fixture()
async def coredns(e: OpsTest, microk8s):
    # bootstrap a juju cloud on the deployed microk8s
    async with microk8s_kubernetes_cloud_and_model(e, "microk8s") as (k8s_alias, _):
        with e.model_context(k8s_alias) as k8s_model:
            LOG.info("Deploy CoreDNS")
            await k8s_model.deploy(
                config.MK8S_CORE_DNS_CHARM,
                application_name="coredns",
                channel=config.MK8S_CORE_DNS_CHANNEL,
                trust=True,
            )
            LOG.info("Create offer for dns-provider")
            await k8s_model.create_offer("coredns:dns-provider", "coredns")
            await k8s_model.wait_for_idle(["coredns"])

        yield k8s_model.applications["coredns"]

        k8s_model.remove_offer("coredns")
        k8s_model.remove_application("coredns", block_until_done=True)


@pytest.mark.abort_on_fail
async def test_core_dns(e: OpsTest, microk8s, coredns):
    machine_model = microk8s.model
    k8s_model = coredns.model
    DNS_TEST = "microk8s kubectl run -i --tty --rm debug --image=busybox --restart=Never -- nslookup google.com"

    try:
        LOG.info("Consume offer for dns-provider")
        await machine_model.consume(f"admin/{k8s_model.name}.coredns", "coredns")
        LOG.info("Add relation between microk8s and coredns")
        await machine_model.add_relation("microk8s", "coredns")
        LOG.info("Wait for idle")
        await asyncio.gather(
            machine_model.wait_for_idle(["microk8s"]), k8s_model.wait_for_idle(["coredns"])
        )

        rc = None
        while rc != 0:
            rc, stdout, stderr = await run_unit(microk8s.units[0], DNS_TEST)
            LOG.info("Verify the pod dns resolution %s", (rc, stdout, stderr))

    finally:
        LOG.info("Remove relation between microk8s and coredns")
        await microk8s.remove_relation("dns", "coredns")
        await asyncio.gather(
            machine_model.remove_saas("coredns"), machine_model.wait_for_idle(["microk8s"])
        )
