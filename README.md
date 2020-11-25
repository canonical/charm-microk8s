# microk8s

## Description

This is a charm for deploying microk8s clusters.  It can handle
scaling up and scaling down.

I'd recommend at least 4G of memory and 2 vCPUs per node, in addition
to the resources required by the applications you plan to deploy.

## Usage

    charmcraft build
    juju deploy --constraints 'cpus=2 mem=4G' ./microk8s.charm

### Scale Out Usage

    juju add-unit -n 2 microk8s

## Developing

Create and activate a virtualenv, and install the development requirements.

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev.txt

## Testing

Just run `run_tests`:

    ./run_tests
