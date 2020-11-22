microk8s handles almost all of the cluster management for us.  We
don't need to know anything about the state of the cluster to manage
it.  All we have to do is call add-node, join, leave, and remove-node
at the appropriate times.

## Cluster Formation

Here's a timeline of how a cluster needs to be formed:

    microk8s/0              microk8s/1              microk8s/2

    install snap            install snap            install snap

    configure proxy         configure proxy         configure proxy

    stop + start            stop + start            stop + start

    add-node                -                       -

    -                       join                    -

    add-node                -                       -

    -                       -                       join

## Unit Removal

Here's what happens when a unit is removed, in this case microk8s/2:

    microk8s/0              microk8s/1              microk8s/2

    cluster-r-departed      cluster-r-departed      -

    -                       -                       cluster-r-broken

    -                       -                       leave

    remove-node             -                       -

Here's an alternative:

    microk8s/0              microk8s/1              microk8s/2

    cluster-r-departed      cluster-r-departed      -

    -                       -                       cluster-r-broken

    remove-node --force     -                       -

We may want to do it this way in case ordering of leave vs remove-node
is important.  Maybe it isn't?

Q: What is the "node" argument to `remove-node`?  Just the name from
`kubectl get nodes`?  No,
[it's an IP address](https://microk8s.io/docs/commands#heading--microk8s-remove-node).
Excellent.

The problem with both schemes above is that we need to run
`remove-node` *after* `cluster-relation-broken` has been handled on
the departing node.  Don't we?
