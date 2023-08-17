# MicroK8s Charm Releases

## Charm branches

Feature development happens in `master`. When a new Kubernetes version `1.xx` is in RC or GA, create a new GitHub issue using the `[Runbook] Create release branch` and follow the steps.

## Tracks and channels

This section describes which channels and tracks are in-use by the MicroK8s charm.

### CharmHub Tracks

At any given point, the following table describes which MicroK8s charm tracks are maintained and in-use:

| CharmHub Track | Snap channel | Charm source branch | Description                                                                                     |
| -------------- | ------------ | ------------------- | ----------------------------------------------------------------------------------------------- |
| latest         | latest/edge  | master              | Built from latest `master` and installs MicroK8s from latest/edge. Not meant for production use |
| 1.29           | 1.29/stable  | release-1.29        | Built from branch `release-1.29`, deploys MicroK8s 1.29 clusters                                |
| 1.28           | 1.28/stable  | release-1.28        | Built from branch `release-1.28`, deploys MicroK8s 1.28 clusters                                |

### CharmHub Channels

| CharmHub channel | Description                        | Release when                                            |
| ---------------- | ---------------------------------- | ------------------------------------------------------- |
| edge             | Built from branch `release-$track` | On every commit after all CI tests pass                 |
| candidate        | Promoted from `edge`               | `edge` is ready for new release                         |
| stable           | Promoted from `candidate`          | `candidate` is tested and is blessed for production use |
