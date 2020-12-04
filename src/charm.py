#!/usr/bin/env python3
# Copyright 2020 Paul Collins
# See LICENSE file for licensing details.

from ops.charm import CharmBase
from ops.main import main

from microk8scluster import MicroK8sCluster


class MicroK8sCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        self.cluster = MicroK8sCluster(self, 'cluster')


if __name__ == "__main__":  # pragma: no cover
    main(MicroK8sCharm, use_juju_for_storage=True)
