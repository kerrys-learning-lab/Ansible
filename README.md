
### Prerequisites

  - https://docs.rke2.io/install/quickstart
    curl -sfL https://get.rke2.io | sudo sh -


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
    `argocd --kubeconfig /etc/kubeconfig-external cluster add --yes default --name wsl --server-name argocd.westsidestreet.net`
