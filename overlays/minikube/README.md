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

The initial end-to-end smoke test registered `average` and `average-3`, then
ran `use_average.ndn` with outputs `15` and `35`. Generated functions can change
on main; that result does not establish execution success for every later
generated function.

`eth0` is the interface observed in this tested setup, not a guarantee for every
Minikube driver or host. Check the node-exporter's `node_network_*` device
labels and adjust `NETWORK_INTERFACE` in `spy-network-metrics-patch.yaml` if
your setup uses a different interface. The selected interface must expose both
receive and transmit byte counters.

## Local settings

- `nfd-storage-patch.yaml` selects the local `standard` StorageClass.
- `image-pull-policy-patch.yaml` reuses cached router and Seed images with
  `IfNotPresent`, so a temporary GHCR/DNS failure does not prevent a restart.
- `function-register-patch.yaml` and `function-invoke-patch.yaml` only adjust
  image pull policies for the generated registration and invocation Jobs.
  `FUNCTION_RUNTIME`, function source, requirements and invocation arguments
  remain as specified in the base manifests. Python functions keep `python`;
  NDN functions keep `ndn`.
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
that Job after NFD, NLSR, Seed and Manager are ready. Generated Job names contain
hashes that can change when the source changes. Select failed Jobs by their
registration/invocation prefixes, and wait for registrations before retrying
invocations:

```powershell
function Remove-FailedFunctionJobs([string]$prefix) {
    $jobs = kubectl --context=minikube -n ndn get jobs -o json | ConvertFrom-Json
    foreach ($job in $jobs.items) {
        $failed = @($job.status.conditions | Where-Object {
            $_.type -eq 'Failed' -and $_.status -eq 'True'
        })
        if ($job.metadata.name.StartsWith($prefix) -and $failed.Count -gt 0) {
            kubectl --context=minikube -n ndn delete job $job.metadata.name
        }
    }
}

Remove-FailedFunctionJobs 'function-register-'
kubectl --context=minikube apply -k overlays/minikube/
$registrationJobs = @(kubectl --context=minikube -n ndn get jobs -o name |
    Where-Object { $_ -like 'job.batch/function-register-*' })
if ($registrationJobs.Count -gt 0) {
    kubectl --context=minikube -n ndn wait --for=condition=complete @registrationJobs --timeout=180s
}

Remove-FailedFunctionJobs 'function-invoke-'
kubectl --context=minikube apply -k overlays/minikube/
$invocationJobs = @(kubectl --context=minikube -n ndn get jobs -o name |
    Where-Object { $_ -like 'job.batch/function-invoke-*' })
if ($invocationJobs.Count -gt 0) {
    kubectl --context=minikube -n ndn wait --for=condition=complete @invocationJobs --timeout=300s
}
kubectl --context=minikube -n ndn logs -l app=function-invoke -c invoker --prefix
```

Before the first apply of a changed Job template, remove the affected failed
Jobs as a group, or apply the long-running workloads separately. Applying an
overlay that changes an existing Job template will report an immutable field
error for that Job. If restarting clients after the routers acquire new Pod
IPs, refresh their DHCP init-container output by rolling out Seed, Manager and
Spy again; their saved `ADDRESS` files refer to the previous router Pod IPs.
