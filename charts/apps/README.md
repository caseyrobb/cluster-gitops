# Workload charts live here, one directory per app:
#   charts/apps/<name>/{Chart.yaml,values.yaml,templates/}
# Managed by argocd/applicationsets/workloads.yaml (project: workloads, namespaced only).

## Pitfall: no Namespace templates here
Namespace is a **cluster-scoped** resource; the `workloads` AppProject
denies cluster-scoped resources (no clusterResourceWhitelist), so any chart
under charts/apps/ that renders one fails every sync with
`resource :Namespace is not permitted in project workloads`. Rely on the
ApplicationSet's `CreateNamespace=true` and set only the namespace NAME in
values.

## VM ignition policy (charts/apps/vm)

Git owns the **Butane source** only (`ignition/*.bnt`). Rendered Ignition
JSON must never be committed — it is produced by `scripts/render-vm-ignition.sh`
and stored in Vault (`chaos/data/vm/<vm>`), from where the chart's
ExternalSecrets sync it into the `cloudInitNoCloud` Secret and the
virtiofs secret volumes. CI compiles every `charts/apps/*/ignition/*.bnt`
with `butane --strict` so the Git copy is always transpilable.
