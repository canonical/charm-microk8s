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

# MK8S_SNAP_CHANNELS is a space-separated list of MicroK8s versions (snap channels) to test.
# A separate test is run for each snap channel.
#   - '1.27 1.26 1.25'          <-- test 1.27, 1.26 and 1.25 MicroK8s channels
#   - '1.27-strict'             <-- test 1.27-strict MicroK8s channel
#   - ''                        <-- test the default MicroK8s channel
MK8S_SNAP_CHANNELS = os.getenv("MK8S_SNAP_CHANNELS", "").split(" ")

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
