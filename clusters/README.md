# Cluster registration (Cluster generator discovery)

Clusters are discovered by the ApplicationSets' **Cluster generator** from Argo CD
cluster Secrets in `openshift-gitops`. A cluster is targeted when it carries:

```yaml
labels:
  argocd.argoproj.io/secret-type: cluster   # set by argocd cluster add / secret creation
  env: homelab                              # the selector both ApplicationSets match
```

## Register this cluster's own API (already the Argo host)

The `in-cluster` secret exists by default; label it so the generators pick it up:

```sh
oc -n openshift-gitops label secret in-cluster env=homelab --overwrite
```

## Register a remote cluster

```sh
argocd cluster add <kubecontext> --name ocp2 --namespace openshift-gitops \
  --label env=homelab,region=lan
```

or hand-write the Secret (server URL, bearer token / client cert) following
https://argo-cd.readthedocs.io/en/latest/operator-manual/cluster-management/

## Name matters

The ApplicationSet templates key on the cluster **`name`** for
`values/clusters/{{.name}}/<chart>.yaml` — the per-cluster values directory must match
the cluster secret's `name` field exactly (currently: `ocp`).

## Removing a cluster

Delete the secret (or drop the `env: homelab` label); Applications are pruned by the
generator. Set `preserveResourcesOnDeletion` in the ApplicationSet template first for
stateful workloads.
