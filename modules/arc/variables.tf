# ============================================================================
# AZURE ARC MODULE
# ============================================================================
# This module manages Azure Arc resources including service principals,
# role assignments, and private link scopes.

variable "project_name" {
  description = "The name of the project"
  type        = string
}

variable "environment" {
  description = "The environment (e.g., dev, staging, prod)"
  type        = string
}

variable "resource_group_id" {
  description = "The ID of the resource group"
  type        = string
}

variable "subscription_id" {
  description = "The subscription ID"
  type        = string
}

variable "arc_service_principal_subscription_scope" {
  description = "Whether to grant Arc service principal permissions at subscription scope"
  type        = bool
  default     = false
}

variable "deploy_arc_private_link_scope" {
  description = "Whether to deploy Arc private link scope"
  type        = bool
  default     = false
}

variable "hub_private_endpoint_subnet_id" {
  description = "The subnet ID for private endpoints"
  type        = string
  default     = null
}

variable "deploy_hub_vnet" {
  description = "Whether to deploy hub VNet"
  type        = bool
  default     = true
}

variable "hub_vnet_id" {
  description = "The ID of the hub virtual network"
  type        = string
  default     = null
}

variable "onprem_vnet_id" {
  description = "The ID of the on-prem (simulated) virtual network for optional DNS links"
  type        = string
  default     = null
}

variable "deploy_onprem_vnet" {
  description = "Whether the on-prem (simulated) VNet is deployed"
  type        = bool
  default     = false
}

variable "private_endpoint_subnet_id" {
  description = "The subnet ID for private endpoints"
  type        = string
  default     = null
}

variable "location" {
  description = "The Azure region for resources"
  type        = string
}
