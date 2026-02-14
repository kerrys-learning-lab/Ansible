# GitLab Hostname Aliasing & Migration Plan

## Problem

Moving GitLab between hosts required a temporary hostname (`gitlab-rehost`) to
avoid conflicts, which meant separate certificates, Ingress rules, and DNS
entries. Clients (git remotes, runners, ArgoCD) had to be reconfigured.

## Solution: Stable Alias + Instance-Specific Hostname

Each GitLab instance gets its own hostname (e.g., `gitlab01`), while a stable
alias (`gitlab`) points to whichever instance is currently active. Clients
always use the alias and never need reconfiguring during migration.

```
Clients → gitlab.westsidestreet.net (stable alias)
                 ↓ CNAME
           gitlab01.westsidestreet.net (instance-specific)
                 ↓ A record
           MetalLB / host IP
```

---

## Architecture

### DNS (Route53)

```
# Instance-specific (A records)
gitlab01.westsidestreet.net      A → <host IP>
registry01.westsidestreet.net    A → <host IP>
minio01.westsidestreet.net       A → <host IP>
kas01.westsidestreet.net         A → <host IP>
pages01.westsidestreet.net       A → <host IP>

# Stable aliases (CNAMEs → active instance)
gitlab.westsidestreet.net        CNAME → gitlab01.westsidestreet.net
registry.westsidestreet.net      CNAME → registry01.westsidestreet.net
minio.westsidestreet.net         CNAME → minio01.westsidestreet.net
kas.westsidestreet.net           CNAME → kas01.westsidestreet.net
pages.westsidestreet.net         CNAME → pages01.westsidestreet.net
```

### Why CNAMEs work transparently

When a browser resolves `gitlab.westsidestreet.net` → CNAME →
`gitlab01.westsidestreet.net` → IP, the HTTP `Host` header still says
`gitlab.westsidestreet.net`. The Kubernetes Ingress matches on the alias
hostname. No `server-alias` annotation is needed.

### TLS Certificates

The cert-manager certificate includes SANs for **both** the alias and
instance-specific hostnames:

```yaml
certificates:
  gitlab-ingress:
    namespace: gitlab-system
    dnsNames:
      - gitlab.westsidestreet.net
      - gitlab01.westsidestreet.net
      - registry.westsidestreet.net
      - registry01.westsidestreet.net
      - minio.westsidestreet.net
      - minio01.westsidestreet.net
      - kas.westsidestreet.net
      - kas01.westsidestreet.net
  gitlab-pages:
    namespace: gitlab-system
    dnsNames:
      - pages.westsidestreet.net
      - "*.pages.westsidestreet.net"
```

This ensures TLS validation succeeds regardless of which hostname is used.

### Kubernetes Ingress

The GitLab Helm chart is configured with `global.hosts.domain: westsidestreet.net`,
which creates Ingress rules matching the **alias** hostnames (`gitlab.westsidestreet.net`,
`registry.westsidestreet.net`, etc.). No changes needed -- the alias is what
clients and Ingress both use.

### What uses the stable alias (no changes during migration)

| Service         | Reference                                  |
|-----------------|--------------------------------------------|
| Git remotes     | `git@gitlab.westsidestreet.net:...`        |
| GitLab Runner   | `gitlabUrl: https://gitlab.westsidestreet.net` |
| ArgoCD repos    | `https://gitlab.westsidestreet.net/api/v4/...` |
| Dependabot      | `gitlabUrl: https://gitlab.westsidestreet.net` |
| Container pulls | `registry.westsidestreet.net/...`          |
| SSH known_hosts | `gitlab.westsidestreet.net`                |
| Helm chart      | `global.hosts.domain: westsidestreet.net`  |

---

## Implementation Steps

### Step 1: Update certificate SANs in `host_vars/gitlab01/gitlab.yaml`

Add instance-specific DNS names to the existing certificate config:

```yaml
  certificates:
    gitlab-ingress:
      namespace: gitlab-system
      dnsNames:
        - gitlab.westsidestreet.net
        - gitlab01.westsidestreet.net          # ADD
        - registry.westsidestreet.net
        - registry01.westsidestreet.net        # ADD
        - minio.westsidestreet.net
        - minio01.westsidestreet.net           # ADD
        - kas.westsidestreet.net
        - kas01.westsidestreet.net             # ADD
```

### Step 2: Create DNS records in Route53

Create A records for the instance-specific hostnames and CNAME records for the
stable aliases (see DNS section above).

### Step 3: Clean up `group_vars/all/main.yaml`

Remove the `gitlab_rehost` FQDN once nvidia-5080 is decommissioned:

```yaml
lan:
  fqdn:
    gitlab: gitlab.westsidestreet.net          # Keep (stable alias)
    # gitlab_rehost: ...                       # Remove
```

### Step 4: Clean up nvidia-5080 rehost config

Once GitLab is running on gitlab01:

1. Delete `host_vars/nvidia-5080/gitlab.yaml`
2. Remove `nvidia-5080` from the `gitlab` group in `inventory/main.yaml`

---

## Future Migration Procedure

When moving GitLab from `gitlab01` to a new instance (`gitlab02`):

### 1. Prepare the new instance

```bash
# Create host_vars/gitlab02/gitlab.yaml
# Copy from gitlab01, update instance-specific names:
#   - Certificate SANs: gitlab02, registry02, minio02, kas02
#   - Everything else stays the same (uses stable aliases)
```

### 2. Add to inventory and deploy

```yaml
# inventory/main.yaml
gitlab:
  hosts:
    gitlab01:
    gitlab02:    # Add new instance
```

```bash
ansible.sh --limit gitlab02 --tags gitlab
```

### 3. Flip DNS

Update Route53 CNAMEs to point to the new instance:

```
gitlab.westsidestreet.net      CNAME → gitlab02.westsidestreet.net
registry.westsidestreet.net    CNAME → registry02.westsidestreet.net
minio.westsidestreet.net       CNAME → minio02.westsidestreet.net
kas.westsidestreet.net         CNAME → kas02.westsidestreet.net
pages.westsidestreet.net       CNAME → pages02.westsidestreet.net
```

### 4. Decommission old instance

1. Remove `gitlab01` from the `gitlab` group in inventory
2. Delete `host_vars/gitlab01/gitlab.yaml`

**Zero client-side changes required.** All git remotes, runners, ArgoCD configs,
and container image references continue to use the stable alias.
