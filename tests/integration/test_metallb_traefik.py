#!/usr/bin/env python3
#
# Copyright 2023 Canonical, Ltd.
#

import logging

import config
import pytest
from conftest import microk8s_kubernetes_cloud_and_model, run_unit
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

LOG = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_metallb_traefik(e: OpsTest, charm_config: dict):
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

    u: Unit = e.model.applications["microk8s"].units[0]

    # bootstrap a juju cloud on the deployed microk8s
    async with microk8s_kubernetes_cloud_and_model(e, "microk8s") as (k8s_model, ns):
        with e.model_context(k8s_model):
            LOG.info("Deploy MetalLB")
            await e.model.deploy(
                config.MK8S_METALLB_CHARM,
                application_name="metallb",
                config={"iprange": "10.42.42.42-10.42.42.42"},
                channel=config.MK8S_METALLB_CHANNEL,
            )
            await e.model.wait_for_idle(["metallb"])
            LOG.info("Deploy Traefik")
            await e.model.deploy(
                config.MK8S_TRAEFIK_K8S_CHARM,
                application_name="traefik",
                channel=config.MK8S_TRAEFIK_K8S_CHANNEL,
                trust=True,
            )
            LOG.info("Deploy hello kubecon")
            await e.model.deploy(
                config.MK8S_HELLO_KUBECON_CHARM,
                application_name="hello-kubecon",
                channel=config.MK8S_HELLO_KUBECON_CHANNEL,
            )
            await e.model.wait_for_idle(["traefik", "hello-kubecon"])
            await e.model.relate("traefik", "hello-kubecon")

        stdout = ""
        while "10.42.42.42" not in stdout:
            rc, stdout, stderr = await run_unit(u, f"microk8s kubectl get svc traefik -n {ns}")
            LOG.info("Check LoadBalancer service %s on %s", (rc, stdout, stderr), ns)

        # Make sure hello-kubecon is available from ingress
        while "Hello, Kubecon" not in stdout:
            rc, stdout, stderr = await run_unit(u, f"curl http://10.42.42.42:80/{ns}-hello-kubecon")
            LOG.info("Waiting for hello kubecon message %s", (rc, stderr))
