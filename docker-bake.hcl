variable "GITHUB_REF_NAME" {
  default = "latest"
}

variable "GITHUB_SHA" {
  default = "latest"
}

target "default" {
  context = "."
  args = {
    REVISION = "${GITHUB_SHA}"
  }
  dockerfile = "Dockerfile"
  tags = ["ghcr.io/semaforinformatik/config-controller:${GITHUB_REF_NAME}", "ghcr.io/semaforinformatik/config-controller:latest"]
  cache-from = ["type=gha,scope=webtens"]
  cache-to = ["type=gha,mode=max,scope=webtens"]
}

