## How can I verify if the inference-gateway exists in the inference namespace and has a valid external address assigned to it?

## What are the specific commands to detect if an inference pod was OOMKilled and to compare its current memory usage against its configured requests and limits?

## How do I check which nodes have allocatable nvidia.com/gpu capacity and verify that the NVIDIA device plugin DaemonSet is running across the cluster?

## If a model rollout appears stuck, how can I check the high-level status of the InferenceService and view the rollout status of the underlying predictor deployment?

## How do I retrieve the logs from the inference-engine container of a specific pod, and how can I access the logs from a previous instance after a container restart?

## What command should I use to view the resource quotas and limit ranges for the inference namespace to see if we have hit a hard cluster-level ceiling?

## How can I audit the container image currently running in each inference pod and compare it with the image defined in the InferenceService specification?

## How do I test if the default ServiceAccount in the inference namespace has the required RBAC permissions to create or update KServe InferenceServices?

## If a node needs maintenance, what is the precise command to drain a node while safely ignoring daemonsets and deleting local emptyDir data?

## How can I monitor the HorizontalPodAutoscaler (HPA) status and run Prometheus queries to check the current concurrent requests and token throughput for my models?