# microk8s

## Description

This is a charm for deploying microk8s clusters.  It can handle
scaling up and scaling down.

I'd recommend at least 4G of memory and 2 vCPUs per node, in addition
to the resources required by the applications you plan to deploy.

## Usage

```bash
juju deploy --constraints 'cores=2 mem=4G' microk8s
```

### Scale Out Usage

```bash
juju add-unit -n 2 microk8s
```

## Testing

### Unit tests

```bash
tox
```

### Integration tests

The integration tests require a bootstrapped Juju controller.

```bash
# preserve the created juju model after tests finish for additional introspection
export MK8S_KEEP_MODEL=1
# specify charmhub name or local path. Set to `build` to build charm from source
export MK8S_CHARM=<path-to-microk8s.charm>
# install microk8s snap from a specific channel, e.g. 1.21
export MK8S_SNAP_CHANNEL=''
# install microk8s charm from a specific channel (ignored if not pulling from CharmHub)
export MK8S_CHARM_CHANNEL=''
# size of cluster to create during the tests
export MK8S_CLUSTER_SIZE=3
# machine constraints for the MicroK8s cluster (passed directly to Juju)
export MK8S_CONSTRAINTS='mem=4G root-disk=20G allocate-public-ip=true'
# optionally, configure an HTTP proxy for the integration tests
export MK8S_PROXY=''

tox -e integration
```
