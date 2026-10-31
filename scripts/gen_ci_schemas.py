#!/usr/bin/env python3
"""Regenerate committed kubeconform schemas (CRD openAPIV3Schema snapshots).

Custom kinds (Vault/ESO/OLM/OpenShift/Argo CD) have no usable schemas in
kubeconform's default store, so schemas are snapshotted here and committed
under .ci/schemas/. kubeconform looks files up as
    <location>/master-standalone[-strict]/<kind>-<group-first-label>-<version>.json
(names harvested from kubeconform's own 'could not find schema' probes).

kubeconform's -strict is defeated by CRD structural schemas because
x-kubernetes-preserve-unknown-fields silently allows unknown fields, so we
inject additionalProperties:false into every typed object node (subtrees that
legitimately preserve unknown fields, e.g. Argo source.helm.parameters, are
left alone).

Regenerate after cluster/ROSG upgrades:
    KUBECONFIG=~/ocp-cluster/ocp.redcomet.ca.kubeconfig python3 scripts/gen_ci_schemas.py
"""
import json
import os
import subprocess
import sys
import urllib.request

# CRDs taken from the LIVE OCP cluster (source of truth for what Argo deploys to).
CLUSTER_CRDS = [
    "clustersecretstores.external-secrets.io",
    "operatorgroups.operators.coreos.com",
    "subscriptions.operators.coreos.com",
    "externalsecretsconfigs.operator.openshift.io",
    "externalsecrets.external-secrets.io",
    "clusterissuers.cert-manager.io",
    "certificates.cert-manager.io",
    "oauths.config.openshift.io",
]

# API kinds served by aggregated apiservers (no CRD objects exist).
OPENAPI_SLICES = [
    ("user.openshift.io", "v1", "Group"),
]

# Argo CD CRDs (match OpenShift GitOps ROSG 1.22.x = Argo CD 3.x).
ARGO_REF = "v3.0.7"
ARGO_CRD_URLS = [
    f"https://raw.githubusercontent.com/argoproj/argo-cd/{ARGO_REF}/manifests/crds/{f}"
    for f in ("application-crd.yaml", "applicationset-crd.yaml", "appproject-crd.yaml")
]

OUT_ROOT = os.path.join(".ci", "schemas")


def strip_and_tighten(node):
    """Make typed objects strict; leave preserve-unknown subtrees untouched."""
    if not isinstance(node, dict):
        return
    if node.get("x-kubernetes-preserve-unknown-fields") is True:
        return  # free-form area — do not enforce additionalProperties here
    node.pop("x-kubernetes-preserve-unknown-fields", None)
    if node.get("type") == "object" or "properties" in node:
        if "properties" in node:
            node.setdefault("additionalProperties", False)
        for v in node.get("properties", {}).values():
            strip_and_tighten(v)
        if isinstance(node.get("additionalProperties"), dict):
            strip_and_tighten(node["additionalProperties"])
    # array element schemas must be tightened too, whether or not the parent
    # is an object node (type: array nodes have no 'properties' — a latent
    # gap that left every identityProviders[]-style item unchecked)
    items = node.get("items")
    if isinstance(items, dict):
        strip_and_tighten(items)
    elif isinstance(items, list):
        for i in items:
            strip_and_tighten(i)
    for key in ("anyOf", "oneOf", "allOf"):
        for v in node.get(key, []):
            strip_and_tighten(v)


def emit(crd_obj):
    kind = crd_obj["spec"]["names"]["kind"].lower()
    group_first_label = crd_obj["metadata"]["name"].split(".", 1)[1].split(".")[0]
    written = 0
    for ver in crd_obj["spec"]["versions"]:
        if not ver.get("served"):
            continue  # e.g. ESO CRDs ship v1beta1 served=false
        schema = ver.get("schema", {}).get("openAPIV3Schema")
        if not schema:
            continue
        strip_and_tighten(schema)
        fname = f"{kind}-{group_first_label}-{ver['name']}.json"
        for mode in ("master-standalone", "master-standalone-strict"):
            out_dir = os.path.join(OUT_ROOT, mode)
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, fname), "w") as f:
                json.dump(schema, f, separators=(",", ":"))
        written += 1
        print(f"  wrote {fname}")
    return written


def _inline_refs(node, defs, seen=()):
    """Replace local $refs with their definitions (cycle-safe)."""
    if isinstance(node, dict):
        if set(node) == {"$ref"}:
            key = node["$ref"].split("/")[-1]
            if key in seen:
                return {"type": "object"}  # recursion guard
            target = defs.get(key)
            if target is None:
                return node
            return _inline_refs(dict(target), defs, seen + (key,))
        return {k: _inline_refs(v, defs, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline_refs(x, defs, seen) for x in node]
    return node


def emit_from_slice(group, version, kind):
    raw = subprocess.run(
        ["kubectl", "get", "--raw", f"/openapi/v3/apis/{group}/{version}"],
        capture_output=True, text=True, check=True,
    ).stdout
    doc = json.loads(raw)
    defs = doc.get("components", {}).get("schemas", {}) or doc.get("definitions", {})
    for name, schema in defs.items():
        gvks = schema.get("x-kubernetes-group-version-kind") or []
        if any(g.get("group") == group and g.get("kind") == kind and g.get("version") == version
               for g in gvks):
            schema = _inline_refs(dict(schema), defs)
            schema.pop("x-kubernetes-group-version-kind", None)
            strip_and_tighten(schema)
            fname = f"{kind.lower()}-{group.split('.', 1)[0]}-{version}.json"
            for mode in ("master-standalone", "master-standalone-strict"):
                out_dir = os.path.join(OUT_ROOT, mode)
                os.makedirs(out_dir, exist_ok=True)
                with open(os.path.join(out_dir, fname), "w") as f:
                    json.dump(schema, f, separators=(",", ":"))
            print(f"  wrote {fname}")
            return 1
    print(f"error: kind {kind} not found in slice {group}/{version}", file=sys.stderr)
    return 0


def main() -> int:
    total = 0
    env = dict(os.environ)
    for crd in CLUSTER_CRDS:
        try:
            raw = subprocess.run(
                ["kubectl", "get", "crd", crd, "-o", "json"],
                env=env, capture_output=True, text=True, check=True,
            ).stdout
        except subprocess.CalledProcessError as e:
            print(f"error: kubectl get crd {crd}: {e.stderr.strip()[:200]}", file=sys.stderr)
            return 1
        total += emit(json.loads(raw))

    for g, v, k in OPENAPI_SLICES:
        total += emit_from_slice(g, v, k)

    import yaml  # noqa: E402 — needed only for the remote CRDs
    for url in ARGO_CRD_URLS:
        with urllib.request.urlopen(url, timeout=60) as r:
            total += emit(yaml.safe_load(r.read().decode()))

    print(f"ok: {total} schema files under {OUT_ROOT}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
