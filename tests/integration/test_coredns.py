#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import logging

import config
import pytest
from conftest import microk8s_kubernetes_cloud_and_model, run_unit
from juju.application import Application
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

LOG = logging.getLogger(__name__)

DNS_TEST = "microk8s kubectl run -it --rm debug --image=busybox:1.28.4 --restart=Never -- nslookup google.com"


@pytest.mark.abort_on_fail
async def test_core_dns(e: OpsTest, charm_config: dict):
    # deploy microk8s
    if "microk8s" not in e.model.applications:
        await e.model.deploy(
            config.MK8S_CHARM,
            application_name="microk8s",
            config={**charm_config, "hostpath_storage": "true"},
            channel=config.MK8S_CHARM_CHANNEL,
            constraints=config.MK8S_CONSTRAINTS,
        )
        await e.model.wait_for_idle(["microk8s"])

    app: Application = e.model.applications["microk8s"]
    unit: Unit = app.units[0]

    # bootstrap a juju cloud on the deployed microk8s
    async with microk8s_kubernetes_cloud_and_model(e, "microk8s") as (k8s_model, model_name):
        with e.model_context(k8s_model):
            LOG.info("Deploy CoreDNS")
            await e.model.deploy(
                config.MK8S_COREDNS_CHARM,
                application_name="coredns",
                channel=config.MK8S_COREDNS_CHANNEL,
                trust=True,
            )
            await e.model.wait_for_idle(["coredns"])

            LOG.info("Create offer for coredns:dns-provider endpoint")
            await e.model.create_offer("coredns:dns-provider", "coredns")

        try:
            LOG.info("Consume coredns:dns-provider and relate with microk8s")
            await e.model.consume(f"admin/{model_name}.coredns", "coredns")
            await e.model.add_relation("microk8s", "coredns")
            await e.model.wait_for_idle(["microk8s"])

            with e.model_context(k8s_model):
                await e.model.wait_for_idle(["coredns"])

            for _ in range(10):
                rc, stdout, stderr = await run_unit(unit, DNS_TEST)
                LOG.info("Verify the pod dns resolution %s", (rc, stdout, stderr))
                if rc == 0:
                    break

            assert rc == 0, "Failed to resolve DNS in 10 tries"

        finally:
            await app.remove_relation("dns", "coredns")
            await e.model.remove_saas("coredns")
            await e.model.wait_for_idle(["microk8s"])
