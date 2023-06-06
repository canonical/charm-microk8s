#
# Copyright 2023 Canonical, Ltd.
#
import json
import os

# MK8S_CHARM is the charm to deploy. Supported values:
#   - 'ch:microk8s'             <-- install charm 'microk8s' from CharmHub
#   - './microk8s.charm'        <-- install from local path
#   - 'build'                   <-- build charm while testing
MK8S_CHARM = os.getenv("MK8S_CHARM", "build")

# MK8S_CHARM_CHANNEL is the CharmHub channel to install from.
#   - 'edge'                    <-- identical to 'juju deploy microk8s --channel edge'
#   - ''                        <-- when installing from local charm, set to empty
MK8S_CHARM_CHANNEL = os.getenv("MK8S_CHARM_CHANNEL", "")

# MK8S_CLUSTER_SIZES is the cluster size to deploy. It is a list of lists of how many
# control plane and how many worker nodes to deploy.
# A separate test is run for each cluster size.
#   - '[[1, 1]]'                <-- (1 test total) 1 control plane and 1 worker node
#   - '[[1, 0], [3, 3]]'        <-- (2 tests total) test 1 control plane and 0 workers,
#                                   test 3 control plane and 3 workers
MK8S_CLUSTER_SIZES = json.loads(os.getenv("MK8S_CLUSTER_SIZES", "[[1, 1]]"))

# MK8S_SERIES is a space-separated list of series to test with.
# A separate test is run for each series.
#   - 'focal jammy'             <-- test with 'focal' and 'jammy'
#   - 'focal'                   <-- test with 'focal' only
#   - ''                        <-- test with default distro
MK8S_SERIES = os.getenv("MK8S_SERIES", "").split(" ")

# MK8S_CONSTRAINTS are constraints for the deployed machines. It is recommended that deployed
# machines have at least 2GB of RAM for the tests to run smoothly.
MK8S_CONSTRAINTS = os.getenv("MK8S_CONSTRAINTS", "mem=4G root-disk=20G")

# MK8S_PROXY is an http-proxy to configure on the machines and containerd.
#   - 'http://proxy:3128'       <-- use 'http://proxy:3128' for http and https traffic
#   - ''                        <-- do not configure proxy
MK8S_PROXY = os.getenv("MK8S_PROXY")

# MK8S_NO_PROXY is the networks to not send through the proxy.
#   - '10.0.0.0/8,127.0.0.1'    <-- set these to the 'NO_PROXY' variable
#   - ''                        <-- do not configure proxy
MK8S_NO_PROXY = os.getenv("MK8S_NO_PROXY")

# MK8S_METALLB_CHARM is the metallb charm for the MetalLB integration tests.
#   - 'ch:metallb'              <-- install charm 'metallb' from CharmHub
MK8S_METALLB_CHARM = os.getenv("MK8S_METALLB_CHARM", "ch:metallb")

# MK8S_METALLB_CHANNEL is the CharmHub channel to use for the metallb charm.
#   - 'edge'                    <-- install charm from 'edge' channel
MK8S_METALLB_CHANNEL = os.getenv("MK8S_METALLB_CHANNEL", "edge")

# MK8S_TRAEFIK_K8S_CHARM is the traefik-k8s ingress charm for the respective integration tests.
#   - 'ch:traefik-k8s'          <-- install charm 'traefik-k8s' from CharmHub
MK8S_TRAEFIK_K8S_CHARM = os.getenv("MK8S_TRAEFIK_K8S_CHARM", "ch:traefik-k8s")

# MK8S_TRAEFIK_K8S_CHANNEL is the CharmHub channel to use for the traefik-k8s charm.
#   - 'edge'                    <-- install charm from 'edge' channel
MK8S_TRAEFIK_K8S_CHANNEL = os.getenv("MK8S_TRAEFIK_K8S_CHANNEL", "edge")

# MK8S_HELLO_KUBECON_CHARM is the hello-kubecon charm for the ingress integration tests.
#   - 'ch:hello-kubecon'        <-- install charm 'hello-kubecon' from CharmHub
MK8S_HELLO_KUBECON_CHARM = os.getenv("MK8S_HELLO_KUBECON_CHARM", "ch:hello-kubecon")

# MK8S_HELLO_KUBECON_CHANNEL is the CharmHub channel to use for the hello-kubecon charm.
#   - 'edge'                    <-- install charm from 'edge' channel
MK8S_HELLO_KUBECON_CHANNEL = os.getenv("MK8S_HELLO_KUBECON_CHANNEL", "edge")

# MK8S_GRAFANA_AGENT_CHARM is the grafana-agent charm for the observability integration tests.
#   - 'ch:grafana-agent'       <-- install charm 'grafana-agent' from CharmHub
MK8S_GRAFANA_AGENT_CHARM = os.getenv("MK8S_GRAFANA_AGENT_CHARM", "ch:grafana-agent")

# MK8S_GRAFANA_AGENT_CHANNEL is the CharmHub channel to use for the grafana-agent charm.
#   - 'edge'                   <-- install charm from 'edge' channel
MK8S_GRAFANA_AGENT_CHANNEL = os.getenv("MK8S_GRAFANA_AGENT_CHANNEL", "edge")

# MK8S_COREDNS_CHARM is the core-dns charm for integration tests.
#   - 'ch:coredns'              <-- install charm 'coredns' from CharmHub
MK8S_COREDNS_CHARM = os.getenv("MK8S_COREDNS_CHARM", "ch:coredns")

# MK8S_COREDNS_CHANNEL is the CharmHub channel to use for the core-dns charm.
#   - 'edge'                    <-- install charm from 'edge' channel
MK8S_COREDNS_CHANNEL = os.getenv("MK8S_COREDNS_CHANNEL", "edge")
