#!/bin/bash -ex

# specify charmhub name or local path. Set to `build` to build charm from source
export MK8S_CHARM=microk8s
# test for multiple snap versions, e.g. '1.21 1.22 1.23' (space separated list)
export MK8S_SNAP_CHANNELS=''
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
