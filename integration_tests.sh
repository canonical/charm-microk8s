#!/bin/bash -ex

# specify charm name to deploy. examples:
#   'ch:microk8s'         -- install charm 'microk8s' from CharmHub.
#   './microk8s.charm'    -- install charm from local path.
#   'build'               -- build charm from source before testing.
export MK8S_CHARM="ch:microk8s"
# specify channel to install microk8s charm from.
export MK8S_CHARM_CHANNEL=edge
# test for multiple snap versions, e.g. '1.21 1.22 1.23' (space separated list)
export MK8S_SNAP_CHANNELS='1.26 1.25 1.24 1.23'
# size of cluster to create during the tests
export MK8S_CLUSTER_SIZE=3
# machine constraints for the MicroK8s cluster (passed directly to Juju)
export MK8S_CONSTRAINTS='mem=4G root-disk=20G'
# machine series to check against (space separated list)
export MK8S_SERIES='focal jammy'
# optionally, configure an HTTP proxy for the integration tests
# export MK8S_PROXY='http://squid.internal:3128'
# export MK8S_NO_PROXY='10.0.0.0/8,127.0.0.0/16,192.168.0.0/16'

tox -e integration
