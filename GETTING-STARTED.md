# Getting Started: Using This Repository for Your Home Lab

This guide walks you through forking and adapting this Ansible repository to
manage your own home lab. It assumes you're new to Ansible but comfortable
with Linux, SSH, and editing YAML files.

---

## Table of Contents

- [What This Repository Does](#what-this-repository-does)
- [Prerequisites](#prerequisites)
- [Step 1: Set Up Your Inventory](#step-1-set-up-your-inventory)
- [Step 2: Verify SSH Connectivity with Ansible Ping](#step-2-verify-ssh-connectivity-with-ansible-ping)
- [Step 3: Configure Secrets](#step-3-configure-secrets)
- [Step 4: Update Network and Domain Settings](#step-4-update-network-and-domain-settings)
- [Step 5: Configure Host Variables](#step-5-configure-host-variables)
- [Step 6: Configure Kubernetes](#step-6-configure-kubernetes)
- [Step 7: Configure GitLab](#step-7-configure-gitlab)
- [Step 8: Configure GitLab Runner](#step-8-configure-gitlab-runner)
- [Step 9: Configure TLS Certificates](#step-9-configure-tls-certificates)
- [Step 10: Run the Playbook](#step-10-run-the-playbook)
- [Key Concepts](#key-concepts)
- [Common Tasks](#common-tasks)
- [Troubleshooting](#troubleshooting)

---

## What This Repository Does

This repository uses Ansible to configure a home lab with:

- **Common Linux configuration** -- packages, DNS, disk management, SMB mounts
- **Kubernetes clusters** using K3S (with support for RKE2 and CRC)
- **Kubernetes ecosystem** -- cert-manager, MetalLB, sealed-secrets, storage classes
- **GitLab** -- deployed via the GitLab Operator on Kubernetes
- **GitLab Runner** -- deployed via Helm on Kubernetes
- **ArgoCD** -- GitOps continuous delivery (optional)
- **NVIDIA GPU drivers** (optional)
- **Development tools** (optional)

The main playbook is `westsidestreet.net.yaml`. You'll rename it for your own
domain (or keep it -- the name is cosmetic).

---

## Prerequisites

### On your control machine (where you run Ansible)

```bash
# Install Ansible
sudo apt install ansible

# Install required Ansible Galaxy collections
ansible-galaxy collection install community.general
ansible-galaxy collection install kubernetes.core
```

### On every target machine

1. **SSH access**: Your user must be able to SSH to each target machine
   without a password (using SSH keys).

2. **Passwordless sudo**: Your user must be able to run `sudo` without
   being prompted for a password.

   ```bash
   # On each target, add your user to sudoers (replace 'youruser'):
   echo "youruser ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/youruser
   ```

3. **Python 3**: Ansible requires Python 3 on target machines (installed by
   default on Ubuntu/Debian).

**Exception**: Proxmox hosts connect as `root` directly (no sudo needed). See
the `group_vars/proxmox/` directory for how this is configured.

---

## Step 1: Set Up Your Inventory

The inventory defines which machines Ansible manages and what groups they
belong to. The existing inventory is at `inventory/main.yaml`.

### Remove the existing inventory

Delete (or completely replace) the contents of `inventory/main.yaml`. The
existing file contains hosts specific to another lab (asus, elitedesk,
gitlab01, nvidia-5080).

### Create your inventory

Create `inventory/main.yaml` with your own hosts. Here's a minimal example for
someone who wants to run GitLab on a single server:

```yaml
all:
  hosts:
    myserver:

# The machine you run Ansible from
ansible:
  hosts:
    myworkstation:

# Hosts that will run GitLab
gitlab:
  hosts:
    myserver:

# Hosts that will run GitLab Runner
gitlab_runner:
  hosts:
    myserver:

# All Kubernetes hosts (using K3S)
k8s:
  children:
    k8s_engine_k3s:
      hosts:
        myserver:

# Ubuntu-based hosts (for OS-specific configuration)
ubuntu:
  hosts:
    myserver:
    myworkstation:
```

A more complete example with multiple machines:

```yaml
all:
  hosts:
    workstation:
    gitlab-server:
    runner-node:

ansible:
  hosts:
    workstation:

gitlab:
  hosts:
    gitlab-server:

gitlab_runner:
  hosts:
    gitlab-server:
    runner-node:

k8s:
  children:
    k8s_engine_k3s:
      hosts:
        gitlab-server:
        runner-node:

# Optional groups -- only include if relevant to your setup
# gpu:
#   children:
#     nvidia:
#       hosts:
#         runner-node:

# development:
#   hosts:
#     workstation:

ubuntu:
  hosts:
    workstation:
    gitlab-server:
    runner-node:
```

### How groups work

Groups control which roles get applied to which hosts:

| Group | What it enables |
|-------|-----------------|
| `all` | Common configuration (packages, DNS, disk management) |
| `ansible` | Installs Ansible tooling on the control host |
| `k8s` / `k8s_engine_k3s` | Installs K3S and Kubernetes ecosystem |
| `gitlab` | Deploys GitLab Operator and GitLab instance |
| `gitlab_runner` | Deploys GitLab Runner via Helm |
| `gpu` / `nvidia` | Installs NVIDIA drivers and container toolkit |
| `development` | Installs development tools |
| `proxmox` | Proxmox-specific configuration |

A host must be in `k8s_engine_k3s` (a child of `k8s`) for Kubernetes to be
installed. Hosts in `gitlab` or `gitlab_runner` must also be in a `k8s` child
group since GitLab runs on Kubernetes.

---

## Step 2: Verify SSH Connectivity with Ansible Ping

Before running any playbooks, verify that Ansible can reach your hosts:

```bash
# Ping all hosts in your inventory
ansible -i inventory all -m ansible.builtin.ping
```

You should see output like:

```
myserver | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

If a host fails, check:

1. **Can you SSH manually?** `ssh myserver` should work without a password
   prompt.
2. **Is Python installed?** Ansible needs Python 3 on the target.
3. **Is the hostname resolvable?** If not, use `ansible_host` in host_vars to
   specify the IP address (see Step 5).

### Test sudo access

```bash
ansible -i inventory all -m ansible.builtin.command -a "whoami" --become
```

Every host should return `root`.

---

## Step 3: Configure Secrets

This repository stores sensitive values (passwords, API keys, SSH keys) in
`group_vars/all/secrets.yaml`. The existing file is encrypted with the original
author's Ansible Vault password, so you need to replace it entirely with your
own values.

You have two options: store secrets as **plain text** (simpler to get started)
or use **Ansible Vault** to encrypt them (more secure, safe to commit).

### Option A: Plain text secrets (simpler)

Delete the existing encrypted file and create a new one with plain text values.
This is the fastest way to get started, but you **must not** commit this file
to version control.

```bash
# Remove the existing vault-encrypted file
rm group_vars/all/secrets.yaml
```

Create a new `group_vars/all/secrets.yaml` with your values in plain text
(see [Secrets structure](#secrets-structure) below for what to put in it).

**Protect your secrets from accidental commits** by adding the file to
`.gitignore`:

```bash
echo "group_vars/all/secrets.yaml" >> .gitignore
```

With plain text secrets, you don't need `--vault-password-file` when running
playbooks:

```bash
ansible-playbook --inventory inventory westsidestreet.net.yaml
```

### Option B: Ansible Vault (encrypted, safe to commit)

Ansible Vault encrypts your secrets file so it can be safely committed to
version control. This is the recommended approach if you plan to keep your
configuration in a Git repository.

```bash
# Generate a strong vault password and save it
openssl rand -base64 32 > ~/.ansible-vault-password
chmod 600 ~/.ansible-vault-password

# Remove the existing file and create a new encrypted one (opens your editor)
rm group_vars/all/secrets.yaml
ansible-vault create --vault-password-file ~/.ansible-vault-password \
  group_vars/all/secrets.yaml
```

Populate it with your secrets (see [Secrets structure](#secrets-structure)
below). To edit it later:

```bash
ansible-vault edit --vault-password-file ~/.ansible-vault-password \
  group_vars/all/secrets.yaml
```

When running playbooks, include the vault password file:

```bash
ansible-playbook \
  --vault-password-file ~/.ansible-vault-password \
  --inventory inventory \
  westsidestreet.net.yaml
```

You can also encrypt individual values inline using `ansible-vault
encrypt_string` (see [Step 8](#step-8-configure-gitlab-runner) for an example).

### Secrets structure

Whether you use plain text or Vault encryption, the file contents are the same.
Here is the structure you need (at minimum for GitLab):

```yaml
secrets_vault:
  # Email for Let's Encrypt certificate registration
  email: you@example.com

  # AWS credentials for Route53 DNS validation (for TLS certificates)
  aws:
    account:
      username: AKIAIOSFODNN7EXAMPLE
      password: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
    route53:
      zoneId: Z1234567890ABC

  # SMB/NAS credentials (remove if you don't have a NAS)
  smb:
    username: smbuser
    password: smbpassword

  # GitLab Runner distributed cache (remove if not using object storage)
  gitlab_runner:
    cache_bucket:
      access_key: minioaccesskey
      secret_key: miniosecretkey

  # GitLab registry database password
  gitlab:
    registry:
      postgresql:
        username: registry
        password: a-secure-password
    backups:
      minio:
        access: minioaccess
        key: miniokey

  # Kubernetes pull secret for private registry (optional)
  k8s:
    glpat: glpat-xxxxxxxxxxxxxxxxxxxx

  # SSH keys for ArgoCD (optional, only if using ArgoCD)
  ssh:
    knownHosts: |
      your-gitlab.example.com ssh-ed25519 AAAA...
    privateKey: |
      -----BEGIN OPENSSH PRIVATE KEY-----
      ...
      -----END OPENSSH PRIVATE KEY-----
```

If you don't need all of these (for example, you have no NAS or don't plan to
use ArgoCD), you can omit the corresponding sections and remove the roles/tasks
that reference them.

---

## Step 4: Update Network and Domain Settings

### Domain and network topology

Edit `group_vars/all/main.yaml` and replace the domain and network values with
your own:

```yaml
ansible_python_interpreter: auto_silent

lan:
  domain: example.com                          # <-- Your domain
  ip:
    ansible: workstation                       # <-- Hostname of your Ansible control machine
    smb: 192.168.1.100                         # <-- Your NAS IP (or remove if no NAS)
    nameserver: 192.168.1.1                    # <-- Your DNS server (often your router)
  fqdn:
    gitlab: gitlab.example.com                 # <-- Where GitLab will be accessible
    minio: minio.example.com                   # <-- GitLab's built-in MinIO
    pages: pages.example.com                   # <-- GitLab Pages (optional)
    registry: registry.example.com             # <-- GitLab container registry
  endpoint:
    # Remove these if you don't have a NAS:
    nas: nas.example.com:5555
    nas_minio: nas-minio.example.com:9000
```

**How to decide what values to use:**

- **`lan.domain`**: Your domain name. If you own `example.com`, use that. If
  you're using a local-only domain, something like `homelab.local` works, but
  you won't be able to get real TLS certificates from Let's Encrypt.
- **`lan.ip.nameserver`**: If you run a local DNS server (like Pi-hole or your
  router's DNS), use its IP. Otherwise use `192.168.x.1` (your router).
- **`lan.fqdn.gitlab`**: The FQDN users will use to access GitLab. You'll need
  a DNS record (A or CNAME) pointing this to your GitLab server's MetalLB IP.
- **`lan.ip.smb`** and **`lan.endpoint.nas*`**: Only needed if you have a NAS
  with SMB shares. Remove these and the corresponding `fstab` configuration in
  `group_vars/all/common.yaml` if you don't.

### Common configuration

Edit `group_vars/all/common.yaml`:

```yaml
all_common:
  # Remove or update the fstab section if you don't have SMB mounts
  fstab:
    smb:
      host: "{{ lookup('ansible.builtin.vars', 'lan').ip.smb }}"
      opts: username=...,password=...
      mounts:
        # Define your SMB mounts, or remove this entire section
        myshare:
          path: my-smb-share

  resolve:
    domain: "{{ lookup('ansible.builtin.vars', 'lan').domain }}"
    nameservers:
      - "{{ lookup('ansible.builtin.vars', 'lan').ip.nameserver }}"
      - 8.8.8.8
      - 8.8.4.4
```

If you have no NAS/SMB shares, remove the `fstab` section entirely.

### Global settings

Review `group_vars/all/global.yaml`. The defaults are sensible for most setups:

```yaml
inherited:
  owner: root
  group: root
  mode: a=rX
  bin: /usr/local/bin
  working: /var/lib/ansible
  install: /usr/local/install
  source: /usr/local/src
  secrets: /usr/local/secrets
  kubeconfig: /etc/kubeconfig
```

You generally don't need to change these unless you have a specific reason.

---

## Step 5: Configure Host Variables

Each host needs a `host_vars/<hostname>/` directory with at least a `main.yaml`
file.

### Create host_vars for each host

First, remove the existing host_vars directories that belong to the original
lab:

```bash
rm -rf host_vars/asus host_vars/elitedesk host_vars/gitlab01 host_vars/nvidia-5080
```

Then create directories for your hosts:

```bash
mkdir -p host_vars/myserver
```

Create `host_vars/myserver/main.yaml`:

```yaml
# How Ansible reaches this host
ansible_fqdn: myserver.example.com
ansible_host: myserver.example.com   # or use an IP: 192.168.1.50
```

If the hostname is directly resolvable via DNS, `ansible_host` can be omitted.

### Common role overrides (optional)

Create `host_vars/myserver/common.yaml` if you need host-specific common
configuration, like disk management:

```yaml
myserver_common:
  fqdn: myserver.example.com

  # Optional: manage disks for Kubernetes local storage
  disk_management:
    disks:
      /dev/sdb:
        label: gpt
        force: true
        partitions:
          - number: 1
            size: 100%
            flags: [lvm]

    volume_groups:
      k8s-storage:
        pvs:
          - /dev/sdb1
        logical_volumes:
          data:
            size: 100%FREE
            filesystem: ext4
            mount: /var/lib/k8s-local-volumes
```

**How to decide**: If your GitLab server has a second disk for data storage,
configure disk management. If you only have a single OS disk and enough space,
you can skip this and the local volumes will be created on the OS disk under
`/var/lib/k8s-local-volumes`.

---

## Step 6: Configure Kubernetes

### K3S engine group

If you're using K3S (the default), verify your hosts are in the
`k8s_engine_k3s` group in your inventory (Step 1).

Review `group_vars/k8s_engine_k3s/main.yaml`. The key settings:

```yaml
k8s_engine_k3s_k8s_engine:
  engine: k3s
  needs:
    certmanager: true     # Required for TLS certificates
    smb: true             # Required for SMB storage -- set to false if no NAS
    metallb: true         # Required for LoadBalancer services
```

Set `needs.smb: false` if you don't have a NAS.

### MetalLB IP pool

Each Kubernetes host needs a MetalLB IP pool -- a range of IP addresses on
your LAN that MetalLB can assign to LoadBalancer services (like GitLab's
ingress).

Create `host_vars/myserver/k8s-ecosystem.yaml`:

```yaml
myserver_k8s_ecosystem:
  metallb:
    pool:
      # Reserve these IPs in your router's DHCP settings so they don't conflict
      - 192.168.1.200-192.168.1.210

  # TLS SANs for the K3S API server (needed for remote kubectl access)
  k3s:
    tls-san:
      - myserver
      - myserver.example.com
      - 192.168.1.50          # The server's IP address

  # Kubernetes secrets needed by cert-manager and storage drivers
  secrets:
    aws:
      type: kubernetes.io/basic-auth
      namespace: infrastructure
      stringData:
        username: "{{ lookup('ansible.builtin.vars', 'secrets_vault').aws.account.username }}"
        password: "{{ lookup('ansible.builtin.vars', 'secrets_vault').aws.account.password }}"
```

**How to decide on the MetalLB pool**: Pick a range of 5-10 IPs on your LAN
that your router's DHCP server will **not** assign to other devices. For
example, if your router assigns DHCP addresses in 192.168.1.100-199, use
192.168.1.200-210 for MetalLB.

### TLS/Certificate infrastructure

Edit `group_vars/k8s/infrastructure.yaml` with your certificate settings:

```yaml
infrastructure_k8s_ecosystem:
  namespaces:
    - infrastructure

  cluster_cert_issuer:
    name: acme-letsencrypt-cluster-issuer
    spec:
      acme:
        email: "{{ lookup('ansible.builtin.vars', 'secrets_vault').email }}"
        server: https://acme-v02.api.letsencrypt.org/directory
        privateKeySecretRef:
          name: acme-letsencrypt-cluster-issuer
        solvers:
          - dns01:
              route53:
                hostedZoneID: "{{ lookup('ansible.builtin.vars', 'secrets_vault').aws.route53.zoneId }}"
                region: us-east-1
                accessKeyIDSecretRef:
                  name: aws
                  key: username
                secretAccessKeySecretRef:
                  name: aws
                  key: password
```

This uses **AWS Route53 for DNS-01 validation** with Let's Encrypt. If you use
a different DNS provider, you'll need to modify the `solvers` section. See the
[cert-manager documentation](https://cert-manager.io/docs/configuration/acme/dns01/)
for other DNS providers (Cloudflare, Google Cloud DNS, etc.).

If you don't have a public domain and just want local-only TLS, consider using
a self-signed ClusterIssuer instead.

---

## Step 7: Configure GitLab

Create `host_vars/myserver/gitlab.yaml`:

```yaml
myserver_gitlab:
  application:
    crd_values:
      inherited:
        common:
          certmanager.k8s.io/issuer: acme-letsencrypt-cluster-issuer
        hosts:
          domain: "{{ lookup('ansible.builtin.vars', 'lan').domain }}"
        ingress:
          configureCertmanager: false
          annotations:
            kubernetes.io/tls-acme: true
            cert-manager.io/cluster-issuer: acme-letsencrypt-cluster-issuer
            nginx.ingress.kubernetes.io/proxy-body-size: 1024m
            nginx.ingress.kubernetes.io/proxy-connect-timeout: 15
            nginx.ingress.kubernetes.io/proxy-read-timeout: 600
            nginx.ingress.kubernetes.io/service-upstream: true
          tls:
            secretName: gitlab-ingress-tls
        kas:
          enabled: true
        pages:
          enabled: true             # Set to false if you don't need GitLab Pages
      gitlab:
        gitaly:
          persistence:
            storageClass: local
            matchLabels:
              owner: gitlab-18.x--gitaly
            size: 100Gi             # Size for Git repository storage
      postgresql:
        install: true
        primary:
          persistence:
            existingClaim: postgresql
      registry:
        enabled: true               # Container registry
        ingress:
          enabled: true
          tls:
            secretName: gitlab-ingress-tls
        database:
          configure: true
          enabled: true
          name: registry
          user: registry
          password:
            secret: gitlab-registry-database-password
            key: password
          migrations:
            enabled: true
      installCertmanager: false

  # Local persistent volumes for GitLab data
  storage:
    local_volumes:
      gitlab-18.x--postgresql:
        capacity: 100Gi             # Size for PostgreSQL database
        path: gitlab-18.x/postgresql
        owner: 1001
        group: 1001
        mode: u=rwx,go=rx
      gitlab-18.x--gitaly:
        capacity: 100Gi             # Size for Gitaly (Git repos)
        path: gitlab-18.x/gitaly
        owner: 1000
        group: 1000
        mode: u=rwx,go=rx

  k8s:
    claims:
      local:
        postgresql:
          volume: gitlab-18.x--postgresql
          capacity: 100Gi

  # TLS certificate for GitLab ingress
  certificates:
    gitlab-ingress:
      namespace: gitlab-system
      dnsNames:
        - gitlab.example.com           # <-- Your GitLab FQDN
        - registry.example.com         # <-- Your registry FQDN
        - minio.example.com            # <-- Your MinIO FQDN
        - kas.example.com              # <-- KAS FQDN (if using)
        - pages.example.com            # <-- Pages FQDN (if using)
        - "*.pages.example.com"        # <-- Wildcard for Pages

  # Backup configuration (optional -- requires MinIO/S3-compatible storage)
  # Remove this section if you don't have backup storage configured
  backups:
    minio:
      base: your-minio.example.com:9000
      bucket: your-minio.example.com:9000
      location: us-east-1
      https: false
      access: "{{ lookup('ansible.builtin.vars', 'secrets_vault').gitlab.backups.minio.access }}"

# Secrets for GitLab (registry database password, backup key)
gitlab_secrets:
  registry:
    postgresql:
      username: "{{ lookup('ansible.builtin.vars', 'secrets_vault').gitlab.registry.postgresql.username }}"
      password: "{{ lookup('ansible.builtin.vars', 'secrets_vault').gitlab.registry.postgresql.password }}"
  backups:
    minio:
      key: "{{ lookup('ansible.builtin.vars', 'secrets_vault').gitlab.backups.minio.key }}"
```

**Key decisions:**

| Setting | How to decide |
|---------|---------------|
| `gitaly.persistence.size` | How much Git repository data you expect. 100Gi is generous for a home lab. |
| `postgresql.capacity` | Database storage. 100Gi is generous; 20Gi is fine for small labs. |
| `pages.enabled` | Set to `true` if you want to host static sites via GitLab Pages. |
| `registry.enabled` | Set to `true` if you want to push/pull Docker images from your GitLab. |
| `kas.enabled` | Set to `true` if you want to use the GitLab Kubernetes Agent. |
| `certificates.dnsNames` | Must include every FQDN GitLab will serve. |
| `backups.minio` | Remove if you don't have S3-compatible backup storage. |

---

## Step 8: Configure GitLab Runner

Create `host_vars/myserver/gitlab-runner.yaml`.

The runner token is obtained after GitLab is running:

1. Deploy GitLab first (Step 10, targeting just GitLab).
2. In GitLab, go to **Admin > CI/CD > Runners** and create a new runner.
3. Copy the registration token.
4. Add it to your `gitlab-runner.yaml` file.

**If using plain text secrets:**

```yaml
myserver_gitlab_runner:
  token: glrt-xxxxxxxxxxxxxxxxxxxx
```

Remember: don't commit this file. Add it to `.gitignore`:

```bash
echo "host_vars/myserver/gitlab-runner.yaml" >> .gitignore
```

**If using Ansible Vault**, encrypt the token inline:

```bash
ansible-vault encrypt_string --vault-password-file ~/.ansible-vault-password \
  'glrt-xxxxxxxxxxxxxxxxxxxx' --name 'token'
```

Paste the output into your file:

```yaml
myserver_gitlab_runner:
  token: !vault |
    <vault-encrypted output>
```

The runner Helm chart defaults (version, namespace, etc.) are in
`roles/gitlab-runner/defaults/main.yaml` and generally don't need changing.

---

## Step 9: Configure TLS Certificates

This repository uses cert-manager with Let's Encrypt for TLS certificates. The
default configuration uses **DNS-01 validation via AWS Route53**.

### What you need

- A domain name you control
- DNS records pointing your GitLab FQDNs to the MetalLB IP that GitLab's
  ingress will receive
- An AWS account with Route53 hosting your domain's DNS zone (or adapt the
  cert-manager solver for your DNS provider)

### DNS records to create

After running the playbook and noting the MetalLB IP assigned to GitLab's
ingress, create these DNS records:

| Type | Name | Value |
|------|------|-------|
| A | gitlab.example.com | `<MetalLB IP>` |
| A | registry.example.com | `<MetalLB IP>` |
| A | minio.example.com | `<MetalLB IP>` |
| A | pages.example.com | `<MetalLB IP>` |
| A | *.pages.example.com | `<MetalLB IP>` |

### Alternative: different DNS provider

If you don't use Route53, edit `group_vars/k8s/infrastructure.yaml` and
replace the `solvers` section. cert-manager supports many providers:
Cloudflare, Google Cloud DNS, DigitalOcean, and more. See the
[cert-manager ACME DNS01 docs](https://cert-manager.io/docs/configuration/acme/dns01/).

---

## Step 10: Run the Playbook

> **Note on Ansible Vault**: If you used Vault encryption in Step 3, add
> `--vault-password-file ~/.ansible-vault-password` to every `ansible-playbook`
> command below. If you're using plain text secrets, omit it.

### Dry run first

Always start with a dry run to see what Ansible would change:

```bash
ansible-playbook \
  --inventory inventory \
  --check \
  westsidestreet.net.yaml
```

### Run incrementally using tags

Rather than running everything at once, bring up your infrastructure in stages:

```bash
# 1. Common configuration (packages, DNS, disk management)
ansible-playbook --inventory inventory --tags common westsidestreet.net.yaml

# 2. Kubernetes engine (K3S installation)
ansible-playbook --inventory inventory --tags k8s-engine westsidestreet.net.yaml

# 3. Kubernetes ecosystem (cert-manager, MetalLB, storage)
ansible-playbook --inventory inventory --tags k8s-ecosystem westsidestreet.net.yaml

# 4. GitLab
ansible-playbook --inventory inventory --tags gitlab westsidestreet.net.yaml

# 5. GitLab Runner (after GitLab is running and you have a runner token)
ansible-playbook --inventory inventory --tags gitlab-runner westsidestreet.net.yaml
```

### Target a specific host

```bash
ansible-playbook --inventory inventory --limit myserver westsidestreet.net.yaml
```

### Run everything

```bash
ansible-playbook --inventory inventory westsidestreet.net.yaml
```

---

## Key Concepts

> For the full architecture reference -- including the secrets pattern, lookup
> conventions, Helm chart structure, Kubernetes resource patterns, and the K8s
> engine abstraction -- see [README.md](README.md). The summaries below cover
> the essentials for getting started.

### Variable Merge Pattern

This is the central design pattern of the repository. Configuration flows from
three levels, with later levels overriding earlier ones:

1. **Role defaults** (`roles/<role>/defaults/main.yaml`) -- baseline values.
   Variable name: `<role>_defaults`.
2. **Group overrides** (`group_vars/<group>/<role>.yaml`) -- apply to all hosts
   in a group. Variable name: `<group>_<role>`.
3. **Host overrides** (`host_vars/<hostname>/<role>.yaml`) -- apply to a single
   host. Variable name: `<hostname>_<role>`.

Each role's first task merges all matching variables using
`community.general.merge_variables`. This means you only need to specify the
values you want to change -- everything else inherits from defaults.

**Example**: To add a package only on your GitLab server, create
`host_vars/myserver/common.yaml`:

```yaml
myserver_common:
  packages:
    - htop
```

This extends (not replaces) the default package list.

### Playbook Structure

The playbook `westsidestreet.net.yaml` runs five plays in order:

1. **Bootstrap Ansible host** -- installs ansible-lint, yamllint, yq
2. **Common configuration** -- packages, DNS, disk management (all hosts)
3. **GPU drivers** -- NVIDIA drivers (nvidia group only)
4. **Kubernetes + applications** -- K3S, ecosystem, GitLab, Runner, ArgoCD
5. **Development tools** -- dev tools (development group only)

### Tags

Every play and role has tags you can use to run specific parts:

| Tag | What it runs |
|-----|-------------|
| `ansible` | Ansible control host setup |
| `common` | Common Linux configuration |
| `gpu`, `nvidia` | GPU drivers |
| `k8s`, `kubernetes` | All Kubernetes plays |
| `k8s-engine` | K3S/RKE2 installation |
| `k8s-tools` | kubectl, helm, k9s, etc. |
| `k8s-ecosystem` | cert-manager, MetalLB, storage |
| `k8s-applications` | Elastic operator, etc. |
| `gitlab` | GitLab and GitLab Runner |
| `gitlab-runner` | GitLab Runner only |
| `argocd` | ArgoCD (if configured) |
| `dev-tools` | Development tools |

---

## Common Tasks

### Rename the playbook

The main playbook is named `westsidestreet.net.yaml`. Rename it to match your
domain:

```bash
mv westsidestreet.net.yaml example.com.yaml
```

Update any wrapper scripts or CI/CD references accordingly.

### Check what would change

```bash
ansible-playbook --inventory inventory --check --diff westsidestreet.net.yaml
```

### Gather facts from all hosts

```bash
ansible -i inventory all -m ansible.builtin.setup --tree /tmp/facts
```

### Encrypt a single value (Vault users only)

```bash
ansible-vault encrypt_string --vault-password-file ~/.ansible-vault-password \
  'my-secret-value' --name 'my_variable'
```

---

## Troubleshooting

### "No such host" or SSH connection failures

- Verify you can `ssh <hostname>` manually
- If the hostname isn't in DNS, set `ansible_host` to the IP address in
  `host_vars/<hostname>/main.yaml`

### "Permission denied" or sudo failures

- Verify passwordless sudo: `ssh <hostname> sudo whoami` should print `root`
  with no password prompt

### "merge_variables" lookup errors

- Install the community.general collection:
  `ansible-galaxy collection install community.general`

### GitLab pods not starting

- Check the MetalLB IP pool has available addresses
- Check cert-manager logs: `kubectl -n cert-manager logs -l app=cert-manager`
- Check GitLab operator logs: `kubectl -n gitlab-system logs -l app=gitlab-operator`
- Verify DNS records point to the correct MetalLB IP
- Verify the TLS certificate was issued: `kubectl -n gitlab-system get certificate`

### "Vault password" errors

- This only applies if you chose Ansible Vault encryption in Step 3
- Ensure `~/.ansible-vault-password` exists and contains your vault password
- Ensure `group_vars/all/secrets.yaml` was encrypted with the same password
- If you're using plain text secrets, make sure you're **not** passing
  `--vault-password-file` (and that `secrets.yaml` has no `$ANSIBLE_VAULT`
  header)
