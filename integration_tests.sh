#!/bin/bash -ex

# preserve the created juju model after tests finish for additional introspection
export MK8S_KEEP_MODEL=1
# specify charmhub name or local path. Set to `build` to build charm from source
export MK8S_CHARM=microk8s
# test for multiple snap versions, e.g. '1.20 1.21 1.22'
export MK8S_SNAP_CHANNELS=''
# size of cluster to create during the tests
export MK8S_CLUSTER_SIZE=3
# machine constraints for the MicroK8s cluster (passed directly to Juju)
export MK8S_CONSTRAINTS='mem=4G root-disk=20G'
# optionally, configure an HTTP proxy for the integration tests
# export MK8S_PROXY='http://squid.internal:3128'
# export MK8S_NO_PROXY='10.0.0.0/8,127.0.0.0/16,192.168.0.0/16'

tox -e integration
