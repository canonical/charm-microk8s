Here's a timeline of how a cluster needs to be formed:

    microk8s/0              microk8s/1              microk8s/2

    install snap            install snap            install snap

    configure proxy         configure proxy         configure proxy

    stop + start            stop + start            stop + start

    add-node                -                       -

    -                       join                    -

    add-node                -                       -

    -                       -                       join
