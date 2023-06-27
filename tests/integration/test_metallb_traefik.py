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
async def test_metallb_traefik(e: OpsTest):
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
    async with microk8s_kubernetes_cloud_and_model(e, "microk8s") as k8s_model:
        with e.model_context(k8s_model) as ns:
            LOG.info("Deploy MetalLB")
            await e.model.deploy(
                config.MK8S_METALLB_SPEAKER_CHARM,
                application_name="metallb-speaker",
            )
            await e.model.deploy(
                config.MK8S_METALLB_CONTROLLER_CHARM,
                application_name="metallb-controller",
                config={"iprange": "42.42.42.42-42.42.42.42"},
            )
            await e.model.wait_for_idle(["metallb-speaker", "metallb-controller"])
            LOG.info("Deploy Traefik")
            await e.model.deploy(
                config.MK8S_TRAEFIK_K8S_CHARM,
                application_name="traefik",
                trust=True,
            )
            LOG.info("Deploy hello kubecon")
            await e.model.deploy(
                config.MK8S_HELLO_KUBECON_CHARM,
                application_name="hello-kubecon",
            )
            await e.model.wait_for_idle(["traefik", "hello-kubecon"])

            u: Unit = e.model.applications["microk8s"].units[0]
            stdout = ""
            while "42.42.42.42" not in stdout:
                rc, stdout, stderr = await run_unit(u, f"microk8s kubectl get svc traefik-k8s -n {ns}")
                LOG.info("Check LoadBalancer service %s", (rc, stdout, stderr))

            LOG.info("LoadBalancer successfully got ExternalIP address")

        #
        #
        #LOG.info("Create a test LoadBalancer service")
        #
        #await run_unit(u, "microk8s kubectl delete service nginx")
        #await run_unit(u, "microk8s kubectl create deploy nginx --replicas 3 --image nginx")
        #await run_unit(u, "microk8s kubectl expose deploy nginx --port 80 --type LoadBalancer")
