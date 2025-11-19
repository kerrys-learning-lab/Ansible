
### Prerequisites

  - https://docs.rke2.io/install/quickstart
    curl -sfL https://get.rke2.io | sudo sh -

NOTE: Prior to installing this package, must perform
    #       - sudo wget -O /etc/apt/sources.list.d/gitlab-ci-local.sources https://gitlab-ci-local-ppa.firecow.dk/gitlab-ci-local.sources
    #       - sudo apt update
    #       as described here: https://github.com/firecow/gitlab-ci-local?tab=readme-ov-file#installation


cd ~/dev/devenv/ansible

```
ansible-playbook --inventory inventory westsidestreet.net.yaml
```

Facts from all hosts:
 ansible -i inventory/ all -m ansible.builtin.setup --tree /tmp/facts

### Add ArgoCD Cluster

1. Update Kubeconfig for external access
    Copy /etc/kubeconfig and replace the loopback addres with the machine's
    IP address or hostname

2. Login to ArgoCD
    `argocd login argocd.westsidestreet.net`

3. Add the Cluster
    `argocd --kubeconfig /var/lib/ansible/kubeconfig.d/... cluster add --yes default --name asusrog --server-name argocd.westsidestreet.net`
