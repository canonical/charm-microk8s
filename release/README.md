The script can be run like

```
sudo snap install charmcraft --classic
sudo snap instal lxd
sudo usermod -a -G lxd $USER
sudo lxd init --auto


charmcraft login --ttl 8766 --export ch.cred
export CHARMCRAFT_AUTH=$(cat ch.cred)


CHANNEL_FROM="1.28/edge" CHANNEL_TO="1.28/beta" python run_release.py
```

however the expected final result will be composed of Jenkins Multibranch Pipelines and matrix of arch, series to cover all testing scenarios.
Each of the stages would be executed on the approriate runner with  