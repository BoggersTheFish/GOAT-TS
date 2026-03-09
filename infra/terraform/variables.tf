variable "kubeconfig_path" {
  description = "Path to kubeconfig used by Terraform."
  type        = string
  default     = "~/.kube/config"
}

variable "namespace" {
  description = "Namespace for TS services."
  type        = string
  default     = "ts-system"
}
