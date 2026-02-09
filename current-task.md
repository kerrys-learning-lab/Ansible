# Task: Apply Ansible to Host `nvidia-5080.westsidestreet.net`


## Situation

The `nvidia-5080.westsidestreet.net` has a Nvidia 5080 GPU and will serve as a
Kubernetes node for running LLM workloads.

After an unsuccessful attempt using Fedora + CRC (CodeReady Containers) -- the
GPU could not be passed through to the CRC VM -- the host has been rebuilt with
**Ubuntu Server**.  The `asus` host is now running **Ubuntu Desktop**.

The host is accessible by FQDN and at IP address `192.168.0.45` and is in the
Ansible inventory.

My user (`kerry`) exists on the machine and has `sudo` privileges.

## Objective

Use Ansible to automate the configuration of `nvidia-5080`, focusing on three
areas:

### 1. Ubuntu Support in `common` Role

Update the `common` role (and any other affected roles) to properly support
Ubuntu.  Both `nvidia-5080` (Ubuntu Server) and `asus` (Ubuntu Desktop) run
Ubuntu, so changes should work for both hosts.

### 2. Nvidia GPU Drivers for Ubuntu

Install and configure the appropriate Nvidia drivers for Ubuntu (replacing any
Fedora-specific driver configuration from the previous attempt).

### 3. k3s as the Kubernetes Engine

Use **k3s** as the Kubernetes distribution on `nvidia-5080`.  The inventory
already reflects this (`nvidia-5080` is listed under the `k3s` group).  The
goal is to get k3s running with GPU access so that workloads like vLLM can
utilize the Nvidia 5080.

### Important Considerations

- The host will serve Large Language Models (LLMs) for usage by other clients
  on the same LAN

- Ideally, the LLMs will be served by vLLM running in the k3s cluster.  If we
  can't get this working, the fallback is Llama.cpp

- We will only run Ansible on the `nvidia-5080.westsidestreet.net` host during
  this effort (i.e., `--limit nvidia-5080`).  This serves the dual purpose of
  reducing the amount of time it takes to determine whether changes to Ansible
  are correct and also narrows the scope of the work.

### Side Goal: Temporarily Host GitLab

A side-goal is to temporarily host a GitLab instance in the host's k3s cluster
so that I can rebuild the current GitLab host (`elitedesk`).

#### Temporary Changes for GitLab Re-host

The following changes are **temporary** and should be reverted once `elitedesk`
is rebuilt and ready to host GitLab again:

| File | Change | Revert Action |
|------|--------|---------------|
| `inventory/main.yaml` | Added `nvidia-5080` to `gitlab` group | Remove `nvidia-5080:` line from `gitlab.hosts` |
| `host_vars/nvidia-5080/gitlab.yaml` | New file: GitLab role config + k8s resources | Delete entire file |

#### DNS Requirement

The following FQDNs must resolve to an IP in nvidia-5080's MetalLB pool
(`192.168.0.200-210`) while GitLab is hosted there:

- `gitlab.westsidestreet.net`
- `registry.westsidestreet.net`
- `minio.westsidestreet.net`
- `kas.westsidestreet.net`
- `pages.westsidestreet.net`

## Key Files

In addition to the Ansible files themselves, the `./README.md` file contains
design and implementation guidance for updating the Ansible scripts.
