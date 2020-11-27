from socket import gethostname

from ops.framework import Object, StoredState

from utils import (
    get_departing_unit_name,
)


class HostnameManager(Object):
    """Declare our hostname to peers, and remember theirs in turn."""
    _state = StoredState()

    def __init__(self, charm, relation_name):
        super().__init__(charm, relation_name)

        self._state.set_default(
            peer_hostnames={},
        )

        self.framework.observe(charm.on[relation_name].relation_created, self._declare_hostname)
        self.framework.observe(charm.on[relation_name].relation_joined, self._remember_hostname)
        self.framework.observe(charm.on[relation_name].relation_changed, self._remember_hostname)
        self.framework.observe(charm.on[relation_name].relation_departed, self._forget_hostname)

    @property
    def peers(self):
        """Return a dict mapping peers' unit names to their hostnames."""
        return dict(self._state.peer_hostnames)

    def _declare_hostname(self, event):
        """Declare our hostname."""
        mydata = event.relation.data[self.model.unit]
        if 'hostname' not in mydata:
            mydata['hostname'] = gethostname()

    def _remember_hostname(self, event):
        """Remember peer hostname."""
        if not event.unit:
            return

        peerdata = event.relation.data[event.unit]
        peer_hostname = peerdata.get('hostname')
        if peer_hostname:
            self._state.peer_hostnames[event.unit.name] = peer_hostname

    def _forget_hostname(self, event):
        """Forget departing peer's hostname."""
        departing_unit = get_departing_unit_name()
        if departing_unit and departing_unit in self._state.peer_hostnames:
            del(self._state.peer_hostnames[departing_unit])
