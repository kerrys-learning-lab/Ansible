# Task: Apply Ansible to Host `nvidia-5080.westsidestreet.net`


## Situation

The `nvidia-5080.westsidestreet.net` was previously an Ubuntu server.  It has
now been rebuilt to use Fedora.  Currently, it is accesible by FQDN and at the
IP address `192.168.0.45` and is in the Ansible inventory.

My user (`kerry`) exists on the machine and has `sudo` privileges.

## Objective

Use Ansible to automate the configuration of the machine and to install
drivers, utilities, and applications.

### Important Considerations

- The host has a Nvidia 5080 GPU (implies the need to install the appropriate
  drivers).

- As previously mentioned, the host is using Fedora.  This leads to a
  preference of using OpenShift Local (aka CodeReady Containers) as the
  Kubernetes engine

- The host will serve Large Language Models (LLMs) for usage by other clients
  on the same LAN

- Ideally, the LLMs will be served by vLLM running in a Kubernetes cluster on
  the machine.  If we can't get this working, the fallback is Llama.cpp

- We will only run Ansible on the `nvidia-5080.westsidestreet.net` host during
  this effort (i.e., I will use `--limit nvidia-5080`).  This serves the dual
  purpose of reducing the amount of time it takes to determine whether changes
  to Ansible are correct and also narrows the scope of the work.

### Side Goal: Temporarily Host GitLab

A side-goal is to temporarily host a GitLab instance in the host's OpenShift
cluster so that I can rebuild the current GitLab host.

## Key Files

In addition to the Ansible files themselves, the `./README.md` file contains
design and implementation guidance for updating the Ansible scripts.
