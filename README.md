TODO:

    - Cert Manager
        Installed via Helm Applications
        Then, need to create an Issuer
        Then, can create k8s certificates


## Ansible

### Prerequisites

#### Install RKE2

[RKE2 Installation Quickstart](https://docs.rke2.io/install/quickstart)

    ```bash
    curl -sfL https://get.rke2.io | sudo sh -
    ```

#### GitLabCI Local

[GitLabCI Local Installation Guide](https://github.com/firecow/gitlab-ci-local?tab=readme-ov-file#installation)

    ```bash
    sudo wget -O /etc/apt/sources.list.d/gitlab-ci-local.sources https://gitlab-ci-local-ppa.firecow.dk/gitlab-ci-local.sources`

    sudo apt update
    ```

#### NVIDIA Container Toolkit

[Installing the NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

    ```bash
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

    sudo apt-get update
    ```

### Running Ansible

cd ~/dev/devenv/ansible

```bash
ansible-playbook    --vault-password-file  ~/.ansible-vault-password \
                    --inventory  inventory \
                    westsidestreet.net.yaml
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
    `argocd --kubeconfig /var/lib/ansible/kubeconfig.d/... cluster add --yes default --name <cluster-name> --server-name argocd.westsidestreet.net`

### GitLab Notes

#### Upgrading GitLab

Last checked:   2026-01-27

| GitLab    | Operator  | Helm chart    |
|---        |---        |---            |
| 18.8.2    | 2.8.2     | 9.8.2         |



https://gitlab.com/gitlab-org/cloud-native/gitlab-operator/-/releases

#### Upgrading the Postgres DB

Run from the machine that has access to the cluster (i.e., `elitedesk`)

```
curl -s "https://gitlab.com/gitlab-org/charts/gitlab/-/raw/${GITLAB_RELEASE}/scripts/database-upgrade" | bash -s -- -n gitlab-system pre
```
