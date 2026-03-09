terraform {
  required_version = ">= 1.7.0"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.35"
    }
  }
}

provider "kubernetes" {
  config_path = var.kubeconfig_path
}

resource "kubernetes_namespace" "ts" {
  metadata {
    name = var.namespace
  }
}

resource "kubernetes_config_map" "ts_runtime" {
  metadata {
    name      = "ts-runtime-config"
    namespace = kubernetes_namespace.ts.metadata[0].name
  }

  data = {
    GRAPH_BACKEND = "nebula"
    SPARK_MODE    = "cluster"
    REDIS_ENABLED = "true"
  }
}
