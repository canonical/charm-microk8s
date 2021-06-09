# microk8s

## Description

This is a charm for deploying microk8s clusters.  It can handle
scaling up and scaling down.

I'd recommend at least 4G of memory and 2 vCPUs per node, in addition
to the resources required by the applications you plan to deploy.

## Usage

    juju deploy --constraints 'cores=2 mem=4G' cs:~pjdc/microk8s

### Scale Out Usage

    juju add-unit -n 2 microk8s

## Testing

Run `tox`
