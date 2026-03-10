# Deploy

Kubernetes deployment configuration.

- `helm/kwyre/` — Helm chart for GPU-accelerated Kubernetes deployment
  - `Chart.yaml` — Chart metadata
  - `values.yaml` — Configurable defaults (model, GPU, persistence, secrets)
  - `templates/` — Deployment, Service, Secret, PVC templates

Install: `helm install kwyre ./deploy/helm/kwyre`
