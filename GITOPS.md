# Monorepo GitOps design for OpenShift multi-cluster using Argo CD ApplicationSets + Helm charts (DRY)

This structure keeps a single repository, packages everything as Helm charts, avoids duplicated Application manifests, and supports arbitrary numbers of clusters with per-cluster custom values. It is designed around ApplicationSet generators (primarily Cluster + Matrix or Git directory) so adding a chart or a registered cluster automatically creates the right Applications.

## Design Principles

- DRY: One Helm chart per component/app. Cluster differences live only in values files (or injected parameters). No copy-paste of manifests or Applications.
- Dynamic multi-cluster: Prefer the Cluster generator so Argo CD discovers clusters from registered cluster Secrets (with labels). New clusters appear automatically once labeled and registered.
- Selective or full deployment: Matrix (charts × clusters) or Cluster + label selectors. Enable/disable or customize via values (`enabled: false` or resource overrides).
- OpenShift-friendly: Works with OpenShift GitOps operator (namespace typically openshift-gitops). Charts can contain Operator Subscriptions, Cluster configs, Routes, SCCs, etc. Use `ServerSideApply=true` and appropriate sync waves where needed.
- Separation: Platform/infra vs workloads; separate AppProjects for RBAC.
- Templating: Enable `goTemplate: true + missingkey=error` for reliable variable substitution (`{{.name}}, {{.server}}`, path helpers, labels).

## Repository Structure

openshift-gitops/
├── README.md
├── bootstrap/                          # Root bootstrap (App-of-Apps or initial ApplicationSet)
│   └── root.yaml
├── argocd/
│   ├── projects/                       # AppProjects (RBAC, source/dest restrictions)
│   │   ├── platform.yaml
│   │   └── workloads.yaml
│   └── applicationsets/                # ApplicationSet definitions
│       ├── platform.yaml               # Core / operators / platform charts
│       └── workloads.yaml              # Application charts
├── charts/                             # All Helm charts (the “what”)
│   ├── platform/
│   │   ├── cert-manager/
│   │   │   ├── Chart.yaml
│   │   │   ├── values.yaml             # Base defaults
│   │   │   └── templates/
│   │   ├── cluster-monitoring/
│   │   ├── oauth/
│   │   └── ...
│   └── apps/
│       ├── my-webapp/
│       │   ├── Chart.yaml
│       │   ├── values.yaml
│       │   └── templates/
│       └── another-service/
│           └── ...
├── values/                             # Cluster-specific overrides (the “how”)
│   └── clusters/
│       ├── prod-cluster-1/
│       │   ├── cert-manager.yaml
│       │   ├── cluster-monitoring.yaml
│       │   └── my-webapp.yaml
│       ├── staging-cluster/
│       │   ├── cert-manager.yaml
│       │   └── my-webapp.yaml
│       └── ...
└── clusters/                           # Optional: documentation or registration helpers
    └── README.md                       # How to register + label clusters


Then reference `values-{{.name}}.yaml` directly. Centralized `values/` scales better when many clusters share charts or when platform teams own overrides separately.

## How ApplicationSets Drive It

1. Register clusters in Argo CD (via CLI, Secret, OpenShift GitOps, or RHACM). Apply consistent labels (e.g. env: prod, tier: critical, region: us-east).
2. ApplicationSets use generators:
- Cluster generator alone — one ApplicationSet per chart (or category) that fans out to matching clusters.
- Matrix generator (preferred for many apps): Git directory generator on charts/platform/* (or charts/apps/*) × Cluster generator. Produces every chart × every matching cluster.
- Optional Git file generator for more complex per-cluster config (e.g. a config.json that lists enabled apps or extra parameters).
3. Template injects:
- Destination: server: `'{{.server}}'` (or name: `'{{.name}}')`.
- Application name: something unique like `{{.name}}-{{.path.basename}}`.
- Helm: path to the chart + layered `valueFiles`.
4. Sync policy: usually automated with prune + selfHeal; add `CreateNamespace=true, ServerSideApply=true`, and `preserveResourcesOnDeletion` where appropriate for stateful or OpenShift resources.

## Example Matrix ApplicationSet (platform charts to all clusters):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: platform
  namespace: openshift-gitops
spec:
  goTemplate: true
  goTemplateOptions: ["missingkey=error"]
  generators:
    - matrix:
        generators:
          - git:
              repoURL: https://gitea.neozeon.ca/crobb/cluster-gitops.git
              revision: HEAD
              directories:
                - path: charts/platform/*
          - clusters:
              selector:
                matchLabels:
                  argocd.argoproj.io/secret-type: cluster
                  # optional further filter: env: prod
  template:
    metadata:
      name: '{{.name}}-{{.path.basename}}'
    spec:
      project: platform
      source:
        repoURL: https://gitea.neozeon.ca/crobb/cluster-gitops.git
        targetRevision: HEAD
        path: '{{.path.path}}'
        helm:
          releaseName: '{{.path.basename}}'
          valueFiles:
            - values.yaml
            - '../../../values/clusters/{{.name}}/{{.path.basename}}.yaml'
          ignoreMissingValueFiles: true   # so missing cluster-specific file is OK
      destination:
        server: '{{.server}}'
        namespace: '{{.path.basename}}'   # or fixed / from values
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
          - ServerSideApply=true
```

Adjust the relative path in valueFiles to match your layout. For co-located values use `values-{{.name}}.yaml` instead.

You can inject dynamic values directly (no extra file) with:

```yaml
helm:
  values: |
    clusterName: {{.name}}
    hostname: {{.name}}.apps.example.com
    replicas: {{ if eq (index .metadata.labels "env") "prod" }}3{{ else }}1{{ end }}
```

or pull from cluster labels/annotations.

## Custom Values Strategy (Multi-Cluster)

- Base always comes from the chart’s `values.yaml`.
- Overrides come from `values/clusters/{{cluster-name}}/{{chart}}.yaml` (or co-located `values-{{name}}.yaml`).
- Missing files are ignored `(ignoreMissingValueFiles: true)`.
- For fine control: set `enabled: false` (and guard templates with `{{- if .Values.enabled }}`) or use different resource limits, image tags, hostnames, storage classes, etc. per cluster.
- Cluster labels can drive additional logic or select which ApplicationSets apply.
- Promote by changing values files or chart versions (pin `targetRevision` or chart version for production).

## Bootstrap & Operations

- Bootstrap with a root Application (or ApplicationSet) that points at argocd/applicationsets/ (and projects). Once the root is applied, everything else is managed by Argo CD.
- Use separate AppProjects for platform vs workloads (restrict destinations, sources, and who can sync).
- Secrets: prefer External Secrets Operator, Sealed Secrets, or OpenShift Secrets management; do not commit plaintext secrets.
- For OpenShift operators: charts can contain Subscription + related CRs; condition them on values.
- Scaling: start with Cluster + label selectors. Add Matrix when you have many charts. For very large fleets, shard ApplicationSets by label (env, region, tier) and monitor ApplicationSet controller resources.
- Progressive delivery: leverage sync waves/phases or ApplicationSet rolling sync strategies.

## Variations

- Per-environment AppSets (instead of one big Matrix) if you want different sync policies or projects per env.
- Git file generator for explicit “which apps on which clusters” config maps/JSON.
- Merge generator for base + per-cluster parameter overrides.
- If using RHACM, you can combine with the clusterDecisionResource generator or placement rules.
- Charts can live in a separate repo (polyrepo) while this monorepo holds only values + ApplicationSets; the structure above still works.
