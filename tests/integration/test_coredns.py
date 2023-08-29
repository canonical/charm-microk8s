#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import logging

import config
import pytest
from conftest import microk8s_kubernetes_cloud_and_model
from juju.application import Application
from pytest_operator.plugin import OpsTest

LOG = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_core_dns(e: OpsTest):
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

    # bootstrap a juju cloud on the deployed microk8s
    async with microk8s_kubernetes_cloud_and_model(e, "microk8s") as (k8s_model, model_name):
        with e.model_context(k8s_model):
            LOG.info("Deploy CoreDNS")
            await e.model.deploy(
                config.MK8S_CORE_DNS_CHARM,
                application_name="coredns",
                channel=config.MK8S_CORE_DNS_CHANNEL,
                trust=True,
            )
            await e.model.wait_for_idle(["coredns"])

            LOG.info("Create offer for dns-provider")
            await e.model.create_offer("coredns:dns-provider", "coredns")

        try:
            LOG.info("Consume offer for dns-provider")
            await e.model.consume(f"admin/{model_name}.coredns", "coredns")
            LOG.info("Add relation between microk8s and coredns")
            await e.model.integrate("microk8s", "coredns")
            LOG.info("Wait for idle")
            await e.model.wait_for_idle(["microk8s"])

            with e.model_context(k8s_model):
                await e.model.wait_for_idle(["coredns"])
        finally:
            app: Application = e.model.applications["microk8s"]
            LOG.info("Remove relation between microk8s and coredns")
            await app.remove_relation("microk8s:dns", "coredns:dns-provider")
            await e.model.remove_saas("coredns")
