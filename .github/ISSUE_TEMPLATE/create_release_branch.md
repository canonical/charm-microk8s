---
name: "[Runbook] Create release branch"
about: Create a new branch for a new stable Kubernetes release
---

#### Summary

Make sure to follow the steps below and ensure all actions are completed and signed-off by one team member.

#### Information

<!-- Replace with the version to create the branch for, e.g. 1.28 -->
- **MicroK8s version**: 1.xx

<!-- Set this to the name of the person responsible for running the release tasks, e.g. @neoaggelos -->
- **Owner**:

<!-- Set this to the name of the team-member that will sign-off the tasks -->
- **Reviewer**:

<!-- Link to PR to initialize the release branch (see below) -->
- **PR**:

#### Actions

The steps are to be followed in-order, each task must be completed by the person specified in **bold**. Do not perform any steps unless all previous ones have been signed-off. The **Reviewer** closes the issue once all steps are complete.

- [ ] **Owner**: Add the assignee and reviewer as assignees to the GitHub issue
- [ ] **Owner**: Ensure that you are part of the ["microk8s developers" team](https://launchpad.net/~microk8s-dev)
- [ ] **Owner**: Request a new `1.xx` CharmHub track for the `microk8s` charm following the [charmstore instructions](https://juju.is/docs/sdk/create-a-track-for-your-charm).
  - #### Post template on https://discourse.charmhub.io/

    **Title:** Request for track 1.xx for the MicroK8s charm

    **Category:** charmhub requests

    **Body:**

      Hi,

      Could we please have a track "1.xx" for the respective MicroK8s charm release?

      Thank you, $name

- [ ] **Owner**: Create `release-1.xx` branch from latest `master`
  - `git checkout master`
  - `git pull`
  - `git checkout -b release-1.xx`
  - `git push origin release-1.xx`
- [ ] **Reviewer**: Ensure `release-1.xx` branch is based on latest changes on master at the time of the release cut.
- [ ] **Owner**: Create PR to initialize `release-1.xx` branch:
  - [ ] Update branch from `master` to `release-1.xx` in [.github/workflows/cla-check.yml](../workflows/cla-check.yml)
  - [ ] Update branch from `master` to `release-1.xx` in [.github/workflows/python.yml](../workflows/python.yml)
  - [ ] Update branch from `master` to `release-1.xx` in [.github/workflows/test.yml](../workflows/test.yml)
  - [ ] Update `cancel-in-progress` from `refs/heads/master` to `refs/heads/release-1.xx` in [.github/workflows/test.yml](../workflows/test.yml)
  - [ ] Update `SNAP_CHANNEL` to `1.xx` in [src/charm_config.py](../../src/charm_config.py)
  - [ ] Update `*_CHANNEL` in [tests/integration/config.py](../../tests/integration/config.py). Kubernetes charms should use `1.xx/stable`, others should use the track against which the microk8s charm should be tested. A stable release for all charms should be preferred unless we are not creating a stable release for microk8s.
  - [ ] `git commit -m 'Release 1.xx'`
  - [ ] Create PR with the changes and request review from **Reviewer**. Make sure to update the issue `Information` section with a link to the PR.
- [ ] **Reviewer**: Review and merge PR to initialize branch.
- [ ] **Owner**: Create launchpad builders for `release-1.xx`
  - [ ] Go to https://code.launchpad.net/~microk8s-dev/charm-microk8s/+git/charm-microk8s and do **Import now** to pick up all latest changes.
  - [ ] Under **Branches**, select `release-1.xx`, then **Create charm recipe**
  - [ ] Set **Owner** to `microk8s-developers`
  - [ ] Set **Charm recipe name** to `microk8s-1.xx`
  - [ ] Enable **Automatically build when branch changes**
  - [ ] Enable **Automatically upload to store**
  - [ ] Set **Registered store name** to `microk8s`
  - [ ] In **Store Channels**, set **Track** to `1.xx` and **Risk** to `edge`. Leave **Branch** empty
  - [ ] Click **Create charm recipe** at the bottom of the page. You will be asked to authenticate with CharmHub so that LaunchPad can automatically push the charm on each build.
- [ ] **Reviewer**: Ensure charm recipe for `release-1.xx` is created
  - List of recipes https://code.launchpad.net/~microk8s-dev/charm-microk8s/+git/charm-microk8s/+charm-recipes
- [ ] **Owner**: Create a release jenkins job to promote jobs from `1.xx/edge` to `1.xx/stable`
  - [ ] Create a PR to include the minor version in https://github.com/charmed-kubernetes/jenkins/blob/main/jobs/release-microk8s.yaml#L215
- [ ] **Reviewer**: Review and merge the PR for the release job.
- [ ] **Owner**: Upload the new job with:
  - `tox --workdir .tox -e py3 -- jenkins-jobs --conf jobs/jjb-conf.ini update jobs/ci-master.yaml:jobs/release-microk8s.yaml` as described in https://github.com/charmed-kubernetes/jenkins/blob/main/docs/index.md#updating-jobs
- [ ] **Reviewer**: Review the created job in jenkins.

#### After release

**Owner** follows up with the **Reviewer** and team about things to improve around the process.
