# cluster-gitops

Monorepo GitOps for Casey's homelab OpenShift cluster (`ocp.redcomet.ca`), driven by
OpenShift GitOps (Argo CD) ApplicationSets + Helm charts (DRY). Design rationale lives
in `GITOPS.md` (also mirrored at
[wiki: Openshift/OCP Homelab Cluster](https://wiki.neozeon.ca/openshift/ocp%20homelab%20cluster)).

## Layout

```
├── bootstrap/            # Apply this first (app-of-apps root)
│   └── root.yaml
├── argocd/
│   ├── projects/         # AppProjects: RBAC boundaries (platform / workloads)
│   └── applicationsets/  # Matrix generators: charts × clusters
├── charts/               # The "what" — one Helm chart per component
│   ├── platform/         # operators, cluster services
│   └── apps/             # workloads
├── values/
│   └── clusters/<name>/  # The "how" — per-cluster overrides, <chart>.yaml
└── clusters/             # Cluster registration how-to
```

## Bootstrap

```sh
oc apply -f bootstrap/root.yaml
```

Argo CD then owns everything under `argocd/` (projects + ApplicationSets), which fan
charts out to every registered, labeled cluster.

## Add an app

1. Chart under `charts/platform/<name>/` or `charts/apps/<name>/` (Chart.yaml, values.yaml, templates/).
2. Optional per-cluster override `values/clusters/<cluster>/<name>.yaml`.
3. Commit — the Matrix generator creates the Application automatically. Disable on a
   cluster with `enabled: false` in its values file.

## Add a cluster

See `clusters/README.md` (register secret + labels; the Cluster generator picks it up).

## Conventions

- Sync: automated, prune, selfHeal, `CreateNamespace=true`, `ServerSideApply=true`.
- `goTemplate: true` with `missingkey=error` everywhere.
- No secrets in git — use External Secrets Operator (Vault) or Sealed Secrets.
