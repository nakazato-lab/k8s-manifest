# Minikube overlay

Run from the repository root against the existing two-node `minikube` cluster:

```powershell
kubectl --context=minikube get nodes
kubectl --context=minikube get namespace ndn
kubectl kustomize overlays/minikube/
kubectl --context=minikube apply -k overlays/minikube/
```

Create the `ndn` namespace first if it does not exist.

## Scope and tested environment

This overlay is an opt-in local development configuration, not a personal
machine configuration. Applying `yaml/` directly does not select these
Minikube patches. The repository-level `.gitattributes` applies independently
to checkouts on all platforms.

Verified on Windows 11, Docker Desktop with the WSL2 backend, Minikube v1.39.0,
Kubernetes v1.37.0, the Docker driver and containerd, with two nodes named
`minikube` and `minikube-m02`. Other developers' machines have not been tested.

`eth0` is the interface observed in this tested setup, not a guarantee for every
Minikube driver or host. Check the node-exporter's `node_network_*` device
labels and adjust `NETWORK_INTERFACE` in `spy-network-metrics-patch.yaml` if
your setup uses a different interface. The selected interface must expose both
receive and transmit byte counters.

## Local settings

- `nfd-storage-patch.yaml` selects the local `standard` StorageClass.
- `image-pull-policy-patch.yaml` reuses cached router and Seed images with
  `IfNotPresent`, so a temporary GHCR/DNS failure does not prevent a restart.
- `function-register-patch.yaml` supplies `FUNCTION_RUNTIME=ndn` for both
  registration Jobs, matching the `.ndn` source in the base manifests.
  This is required by the registerer image used in this verification regardless
  of the Kubernetes environment; it is not inherently a Minikube setting.
  It is currently kept here to preserve the original lab manifests.
- The Function Job patches also use `IfNotPresent`. A node still needs registry
  access the first time it uses an image that is not cached there. Cached
  `latest` images do not update automatically under this policy.
- `spy-network-metrics-patch.yaml` mounts the local `network_metrics.py` and
  selects `NETWORK_INTERFACE=eth0`. The image hard-codes the lab NIC `ens18`,
  which has no matching metrics on Minikube and makes resource replies fail.
  Only the NIC selection is adapted; sampling and the lab's assumed 1Gbps
  capacity remain unchanged. That capacity is not a measured virtual NIC speed.
  The mounted module is adapted from the tested Spy image. Review compatibility
  when updating that image; this does not change the upstream image itself.

`conf/*.sh` and `conf/*.conf` must use LF line endings. The repository's
`.gitattributes` preserves LF on Windows. Kustomize copies these file bytes into
the ConfigMap; CRLF makes `/bin/sh` fail at `set -eu` with `Illegal option -`.
The base configuration content is unchanged apart from line endings.

## Retry failed Function Jobs

Job Pod templates are immutable and an exhausted Job does not restart when
applied again. Preserve logs before deleting a failed Job, then recreate only
that Job after NFD, NLSR, Seed and Manager are ready. For the current manifests:

```powershell
kubectl --context=minikube -n ndn delete job function-register-average-074aab6fa5d9 function-register-average-3-f0ef687a85c9
kubectl --context=minikube apply -k overlays/minikube/
kubectl --context=minikube -n ndn wait --for=condition=complete job/function-register-average-074aab6fa5d9 job/function-register-average-3-f0ef687a85c9 --timeout=180s
kubectl --context=minikube -n ndn delete job function-invoke-use-average-872195af89b7
kubectl --context=minikube apply -k overlays/minikube/
kubectl --context=minikube -n ndn logs job/function-invoke-use-average-872195af89b7
```

Before the first apply of a changed Job template, remove the affected failed
Jobs as a group, or apply the long-running workloads separately. Applying an
overlay that changes an existing Job template will report an immutable field
error for that Job. If restarting clients after the routers acquire new Pod
IPs, refresh their DHCP init-container output by rolling out Seed, Manager and
Spy again; their saved `ADDRESS` files refer to the previous router Pod IPs.
