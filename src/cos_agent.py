#
# Copyright 2023 Canonical, Ltd.
#
from charms.grafana_agent.v0.cos_agent import COSAgentProvider


class Provider(COSAgentProvider):
    @property
    def _scrape_jobs(self):
        return self._metrics_endpoints()
