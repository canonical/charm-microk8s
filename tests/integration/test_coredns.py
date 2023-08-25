#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import logging

import config
import pytest
from conftest import microk8s_kubernetes_cloud_and_model
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
                trust=True,
            )
            await e.model.wait_for_idle(["coredns"])

            LOG.info("Create offer for dns-provider")
            await e.model.create_offer("coredns:dns-provider", "coredns")

        try:
            await e.model.consume(f"admin/{model_name}.coredns", model_name)
            await e.model.add_relation("microk8s", "coredns")
            await e.model.wait_for_idle(["microk8s"])

            with e.model_context(k8s_model):
                await e.model.wait_for_idle(["coredns"])
        finally:
            await e.model.remove_saas("coredns")
