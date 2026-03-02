# Kubernetes example manifests for Draft UI

Example Deployment, Service, ConfigMap, Secret, RBAC, and PVCs for running Draft in Kubernetes. See [docs/container-orchestration-guide.md](../docs/container-orchestration-guide.md) for the full container orchestration guide.

## Apply order

1. `pvc.yaml` — PersistentVolumeClaims for data and HF cache
2. `configmap.yaml` — Non-sensitive config (edit `DRAFT_LLM_ENDPOINT`, model names, etc.)
3. `secret.yaml` — Add API keys if needed (e.g. `DRAFT_LLM_API_KEY` for OpenAI-compatible endpoint)
4. `rbac.yaml` — ServiceAccount, Role, RoleBinding
5. `deployment.yaml` — Draft UI Deployment (uses `draft-ui:latest`; set your image and namespace)
6. `service.yaml` — ClusterIP Service on port 8058

## Customize

- **Namespace:** Change `namespace: default` in all files to your namespace.
- **Image:** Set `image` in `deployment.yaml` to your registry image (e.g. `myreg/draft-ui:latest`).
- **LLM:** Set `DRAFT_LLM_ENDPOINT` in ConfigMap to your Ollama Service URL or OpenAI-compatible gateway; add `DRAFT_LLM_API_KEY` and `DRAFT_LLM_MODEL` in Secret/ConfigMap if using that path.
- **Storage:** Adjust `storageClassName` and `storage` in `pvc.yaml` for your cluster.
