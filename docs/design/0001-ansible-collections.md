# ADR 0001: Extract shared Ansible roles into versioned collections

- **Status:** Accepted
- **Date:** 2026-06-13
- **Deciders:** Kerry, Claude
- **Related:** [#19] (this work), [#17] (cloud-gpu host)

## Context

We want the Cloud GPU (`cloud-lab/cloud-gpu`) to be **self-contained**: it should
have its own Ansible configuration and **no dependency on Home-Lab-specific
Ansible**. Today, all Ansible for the home lab lives in a single repository
(`devsecops/ansible`) — 15 roles plus inventory, playbook, and vars — and
`cloud-gpu` is just another inventory host within it.

Analysis of the current repo produced three findings that shape this decision:

1. **The roles are loosely coupled.** There are no `include_role` / `import_role`
   calls between roles and no declared `meta/dependencies`; each role owns its own
   `*_defaults` variable namespace. The only coupling is (a) **playbook ordering**
   (e.g. `k8s-engine` → `k8s-ecosystem` → `k8s-applications`) and (b) **shared
   `group_vars`**. Neither lives inside a role, so roles can be relocated freely.

2. **The real Home-Lab entanglement is the *data layer*, not the role code.** The
   coupling that actually binds `cloud-gpu` to the home lab is the `global`
   god-object var (which transitively pulls the ~745-line `secrets_vault`) and
   `group_vars/k8s/infrastructure.yaml` (route53 DNS-01, SMB creds, AWS account
   creds). The role *logic* is already parameterised and reusable.

3. **The Cloud GPU's essential secret footprint is ~zero.** Its vLLM model
   (`Qwen2.5-Coder`) is ungated (no HF token), its certs use `http01` via Traefik
   (no route53 DNS-01), and SSH uses a file-based AWS `.pem`. Its dependency on
   `secrets_vault` is *incidental* (inherited via shared vars), not *essential*.

Therefore the problem decomposes into two independent pieces of work:

- **This ADR — sharing the role *code*** so both labs run the same roles without
  copy-paste.
- **The data layer** (a minimal Cloud-only vars/secrets set) — required regardless
  of how role code is shared, and **out of scope here** (tracked separately).

## Decision

### 1. Extract the shared roles into two versioned Ansible **collections**

| Collection | Roles | Consumed by |
| --- | --- | --- |
| `kerrys_learning_lab.base` | `common`, `nvidia`, `certbot`, `ansible` | Home Lab, Cloud Lab |
| `kerrys_learning_lab.kubernetes` | `k8s-engine`, `k8s-tools`, `k8s-ecosystem`, `k8s-applications`, `k8s-share`, `argocd` | Home Lab, Cloud Lab |

The split line is drawn on the **consumption boundary** — i.e. *what the Cloud Lab
actually needs* — not on taxonomy. Cloud Lab consumes `base` + `kubernetes`; Home
Lab consumes both plus its own local roles.

### 2. Leave Home-Lab-only roles as plain roles in `devsecops/ansible`

`gitlab`, `gitlab-runner`, `dev-tools`, `proxmox`, and `raspberry-pi` are
single-consumer today. **Collection membership is earned by a sharing or
independent-versioning need, not by taxonomy** — a role does not need to be in a
collection to be used. These stay as plain roles in this repo and are promoted
only when a second consumer or a real versioning need appears. See
[Future collections](#future-collections-not-built-now).

### 3. One repo per collection, under the `ansible-collections` sub-group

- `devsecops/ansible-collections/base`
- `devsecops/ansible-collections/kubernetes`

**Separate repositories, not a monorepo.** Git tags are repo-wide, so co-locating
the collections would re-couple their versions at the tag layer — defeating the
independent change-rate that motivated splitting them. Separate repos give each
collection one clean `vX.Y.Z` timeline, independent Renovate tracking, and a
simple `galaxy.yml`-at-root / CI-lint-and-build / semver-tag convention (the
mainstream one-repo-per-collection pattern).

### 4. Distribute via **Git reference** — no publish step

Collections are consumed straight from GitLab over SSH in `requirements.yml`.
There is no build/upload/registry step; **"publishing" is pushing a git tag.**

```yaml
# requirements.yml (consumer side)
collections:
  - name: git+ssh://git@gitlab.westsidestreet.net/kerrys-learning-lab/devsecops/ansible-collections/base.git
    type: git
    version: v1.0.0          # any git ref — tag, branch, or SHA
  - name: git+ssh://git@gitlab.westsidestreet.net/kerrys-learning-lab/devsecops/ansible-collections/kubernetes.git
    type: git
    version: v1.0.0
```

Then `ansible-galaxy collection install -r requirements.yml`. This reuses the
existing GitLab + SSH-key auth and adds zero new infrastructure.

*Future options if needed (not now):* build a tarball
(`ansible-galaxy collection build`) and host it in the GitLab generic Package
Registry for immutable artifacts; a private Galaxy server (Automation Hub / Pulp)
is overkill for two consumers.

### 5. Compose collections at the **playbook layer** — no inter-collection deps

`galaxy.yml` will **not** declare `kubernetes` → `base` as a dependency. Both the
Home-Lab and Cloud-Lab playbooks list `base` then `kubernetes` in their own
`requirements.yml`. This keeps the two collections independently versionable and
avoids version lock-step. (Declaring the dependency would let consumers list only
`kubernetes` and pull `base` transitively — convenient, but it couples their
version ranges. The explicit two-line `requirements.yml` is clearer and looser.)

### 6. Fully-qualified role names and the hyphen → underscore rename

Inside collections, roles are referenced by FQCN, e.g.
`kerrys_learning_lab.base.common`, `kerrys_learning_lab.kubernetes.k8s_engine`.
Because collection namespace/name and role names must be valid Python identifiers,
hyphenated role directories are renamed to underscores (`k8s-engine` → `k8s_engine`,
`k8s-ecosystem` → `k8s_ecosystem`, etc.). Playbooks are updated to FQCN once.

### 7. The data layer is separate, unavoidable work

Building a minimal Cloud-only vars/secrets layer (replacing the `global` /
`secrets_vault` / `group_vars/k8s/infrastructure` assumptions) is required no
matter how role code is shared, and is **not** part of the collections. It is the
*data* that stays in each consumer's inventory layer; collections carry only role
logic and sane defaults.

### 8. Development workflow — fast iteration via a local collection path

Git-referencing means a naive change cycle is *edit → commit → tag → bump → re-install*.
For active development, **symlink a working clone into the collection path** so
edits are picked up live, and only cut a tag when a release is ready:

```bash
# one-time, per collection
mkdir -p ~/.ansible/collections/ansible_collections/kerrys_learning_lab
ln -s ~/dev/kerrys-learning-lab/devsecops/ansible-collections/base \
      ~/.ansible/collections/ansible_collections/kerrys_learning_lab/base
ln -s ~/dev/kerrys-learning-lab/devsecops/ansible-collections/kubernetes \
      ~/.ansible/collections/ansible_collections/kerrys_learning_lab/kubernetes
```

Equivalently, point `ANSIBLE_COLLECTIONS_PATH` at a tree containing the clones.
This gives fast local iteration *and* clean pinned releases. **This workflow must
be documented in each collection's README.**

## Alternatives considered

- **Fork the roles into the Cloud Lab.** Copy the needed roles into `cloud-lab`.
  Truly independent and fastest, but duplicates ~2k lines of actively-maintained
  role code that then diverges. Rejected in favour of shared, versioned code.
- **Reference the Home-Lab roles via git submodule / requirements pointing at
  `devsecops/ansible`.** Lightest, but keeps a live dependency on the Home-Lab
  repo — "independent" in name only. Rejected; it defeats the goal.
- **One big collection** (all shared roles together). Simplest to version once,
  but the Cloud Lab would pull a fat, dishonest dependency (gitlab/proxmox/pi it
  never runs) and versioning would be coarse. Rejected.
- **Monorepo of two collections** (both in one repo, subdir installs). Possible,
  but repo-wide tags force a prefixed-tag convention and complicate Renovate to
  recover the version independence separate repos give for free. Rejected.
- **Private Galaxy server (Automation Hub / Pulp).** True publish semantics, but a
  whole service to run for two consumers. Overkill. Rejected.

## Consequences

**Positive**

- The Cloud Lab takes an **honest, minimal dependency** (`base` + `kubernetes`),
  expressing the independence goal cleanly.
- Each collection is **independently versioned**; change-rate is decoupled.
- Role code is **shared without copy-paste**; no divergence/double-maintenance.
- Forces extraction of the Home-Lab `global` god-object — a longstanding smell —
  out of the shared role path.
- **Renovate** can manage version bumps as explicit, reviewable MRs, turning
  "the Cloud box silently inherited a Home-Lab change" into a deliberate adoption.

**Negative / costs**

- Up-front refactor: extract roles, stand up two repos + CI, rename hyphenated
  roles, convert playbooks to FQCN.
- More repositories to manage (mitigated by templated CI).
- The data-layer trim is still required separately (unavoidable in every option).
- Cross-domain changes that touch both collections now span two repos.

## Migration path

1. Create the two repos under `devsecops/ansible-collections/` with `galaxy.yml`,
   CI (lint + build), and README (incl. the dev-workflow section).
2. Move `base` roles, then `kubernetes` roles, into their collections (rename
   hyphens → underscores). Tag `v1.0.0` each.
3. Convert `devsecops/ansible` into a **consumer**: add `requirements.yml`
   referencing both collections; update the playbook to FQCN; delete the moved
   roles. The Home Lab is now the first proof that the collections work.
4. (Separate issue) Build the Cloud-only vars/secrets layer and a thin Cloud-Lab
   playbook + inventory consuming the same two collections at its own pinned
   versions.

## Future collections (not built now)

If a second consumer or independent-versioning need later appears, the natural
homes for the Home-Lab-only roles are:

- `kerrys_learning_lab.cicd` — `gitlab`, `gitlab-runner`
- `kerrys_learning_lab.workstation` — `dev-tools` (the "coding" environment; would
  graduate to shared if we ever develop *on* the Cloud GPU)
- `kerrys_learning_lab.platform` — `proxmox`, and `raspberry-pi` *if it returns*

`raspberry-pi` is deliberately **not** categorised now (unused for years — YAGNI);
it stays a dormant role until picked back up.

[#17]: https://gitlab.westsidestreet.net/kerrys-learning-lab/devsecops/ansible/-/issues/17
[#19]: https://gitlab.westsidestreet.net/kerrys-learning-lab/devsecops/ansible/-/issues/19
