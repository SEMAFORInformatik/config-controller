# Config controller

The config-controller is a python application that manages application jobs in a Kubernetes environment.

To run this in a cluster you can use the provided helm chart and install it.
Alternatively you can make use of [Skaffold](https://skaffold.dev/) to run with auto-reload for development.

## Registering application templates

The config-controller uses [configmaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
to create and list instances of applications.

The configmap needs to have the label `config-controller.semafor.ch/template`, and
contain a yaml file with the job template (what you'd put into the /spec/template key in a job object)
to be recognized by the config-controller.

It will also only look for the configmaps within the same namespace it's deployed in.

Example:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: scim-config
  labels:
    config-controller.semafor.ch/template: 'true'
data:
  scim-intens.yaml: |-
    metadata:
      labels:
        app.kubernetes.io/name: scim
        app.kubernetes.io/instance: scim
    spec:
      terminationGracePeriodSeconds: 0
      restartPolicy: Never
      containers:
        - image: "hub.semafor.ch/semafor/scim:latest"
        ...
    
```

The label needed to search for the config-controller is also adjustable
via the value customConfigSelector in the helm chart.

Changes done to the template in the configmap will apply to future applications started with it.
Already running applications will not be affected by changes to the template.

Removing an application type requires you to just delete the configmap itself. Please note that already running applications
are still deletable and listed via the API.

## REST API

The REST API consists of 4 routes:

* `GET /app`: Return a list of all available app types to deploy.
* `GET /app/<type>`: Return a list of all running instances of a specific app type.
  It includes information like ip address and startup time.
* `GET /app/<type>/<name>`: Get the address of the app of a type and name.
  If no instance of said name is running, a new app will be started.
* `PATCH /app/<type>/<name>`: Add labels to a running instance. For example username, sessionID
* `DELETE /app/<type>/<name>`: Stop a running app with said type and name.

If you try to start an app that does not exist as a type or the template contains errors, a relevant error message will be shown.

Jobs started with the config-controller have relevant labels applied under the `config-controller.semafor.ch/` namespace.
