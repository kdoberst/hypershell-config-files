# A Beginner’s Guide to HyperShell: Running a Prompt from GitHub Actions with the CLI

You already have a GitHub repository, and you want a secure place to run an AI prompt against that repository without tying up your laptop. That is exactly what HyperShell is for!

In this walkthrough, we will use the GitHub CLI to create a HyperShell sandbox, run a prompt inside it, download the result, and clean the sandbox up when the run finishes. Everything happens from the command line; you will not need the HyperShell UI.

By the end, you will have:

* A HyperShell gateway and workspace
* A service account that GitHub Actions can use
* An EnMaaS provider for the model
* A GitHub provider so the sandbox can clone your repository
* A reusable sandbox template
* A GitHub Actions workflow that creates, runs, and deletes a sandbox on demand

## 1. Gather Your Prerequisites

Because your secure sandbox needs permission to connect to outside systems on your behalf, we need to gather three secure keys.

Please generate and have the following ready:

* [EnMaaS key](https://source.redhat.com/departments/products_and_global_engineering/workload_management/enmaas)
* [GitHub personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
* [Jira API token](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/)

You will also need:

* [HyperShell CLI (hsctl)](https://github.com/openshift-online/hypershell/releases/latest)
* The [OpenShell CLI](https://docs.nvidia.com/openshell/latest/about/installation) or run `brew install openshell` on macOS
* [jq,](https://jqlang.org/download/) if you want to copy and paste the gateway ID extraction command

We will store the EnMaaS key and GitHub token as HyperShell providers, so they never need to appear in your repository.

## 2. Log In to HyperShell

`hsctl` talks to the HyperShell control plane. It is the tool you will use to create your gateway.

Log in with:

```bash
hsctl login --url https://api.hyp2.infra.hypershell.app/
```

This opens a browser and saves your HyperShell credentials locally.

## 3. Create Your Gateway

A gateway is your dedicated home base in HyperShell. It owns your workspaces, profiles, providers, templates, and sandboxes.

Set a friendly gateway name and workspace:

```bash
GATEWAY_NAME=github-cli
WORKSPACE=default
```

Create the gateway on the public IBM Cloud:

```bash
hsctl create gateway \
  --name "$GATEWAY_NAME" \
  --placement-selector network/public \
  --placement-selector provider/ibm
```

Then capture the gateway ID:

```bash
GATEWAY_ID="$(hsctl list gateways -o json | jq -r --arg name "$GATEWAY_NAME" '.items[] | select(.name == $name) | .id')"
```

Confirm that the ID was found:

```bash
echo "$GATEWAY_ID"
```

## 4. Connect the OpenShell CLI to Your Gateway

`openshell` talks to the gateway itself. It is the tool you will use to manage profiles, providers, templates, and sandboxes.

Ask HyperShell for the exact connection command:

```bash
hsctl get gateway "$GATEWAY_ID" --show-connection
```

Copy the `openshell gateway add ...` command from that output and run it in your terminal.

Then log in to the gateway:

```bash
openshell gateway login "$GATEWAY_NAME"
```

## 5. Create a Service Account

A service account lets GitHub Actions authenticate to HyperShell without using your personal login.

Create one for this gateway:

```bash
hsctl create serviceAccount \
  --gateway-id "$GATEWAY_ID" \
  --name github-actions \
  --output-file service-account.json
```

This creates a mode-`0600` JSON file containing the service-account credentials. Treat it like a password.

Extract the values you will need later:

```bash
SERVICE_ACCOUNT_SUBJECT="$(jq -r '.subject' service-account.json)"
GATEWAY_URL="$(jq -r '.credential.gateway_endpoint' service-account.json)"
OIDC_ISSUER="$(jq -r '.credential.issuer' service-account.json)"
OIDC_CLIENT_ID="$(jq -r '.credential.client_id' service-account.json)"
OIDC_AUDIENCE="$(jq -r '.credential.audience' service-account.json)"
OPENSHELL_OIDC_CLIENT_SECRET="$(jq -r '.credential.client_secret' service-account.json)"
```

## 6. Add the Service Account to Your Workspace

The service account needs permission to use your gateway workspace.

Add it with:

```bash
openshell -g "$GATEWAY_NAME"  workspace member add \
  --workspace "$WORKSPACE"\
  --subject "$SERVICE_ACCOUNT_SUBJECT" \
  --role user
```

## 7. Import Profiles

Profiles are reusable blueprints. They tell HyperShell which external systems a sandbox may reach and which binaries are allowed to reach them.

We need two profiles:

* EnMaaS, for the model
* GitHub, for cloning your repository and reading repository data

Import the EnMaaS profile:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" profile import \
  --url https://raw.githubusercontent.com/kdoberst/hypershell-config-files/refs/heads/main/profiles/enmaas.yaml
```

Import the GitHub profile:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" profile import \
  --url https://raw.githubusercontent.com/ai-openshell/openshell/refs/heads/main/providers/github.yaml
```

Confirm the profiles are available:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" profile list
```

These profiles carry the network rules the sandbox needs. You do not need a separate sandbox policy file for this walkthrough.

## 8. Create Providers

If profiles are blueprints, providers are secure vaults. A provider stores the real credentials that a profile references.

Export your secrets as environment variables:

```bash
export ANTHROPIC_API_KEY="<your-enmaas-key>"
export GITHUB_TOKEN="<your-github-token>"
```

Create the EnMaaS provider:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" provider create \
  --name enmaas-claude \
  --type enmaas-claude \
  --credential ANTHROPIC_API_KEY
```

Create the GitHub provider:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" provider create \
  --name github \
  --type github \
  --credential GITHUB_TOKEN
```

These providers can stay in your workspace and be reused by future sandboxes.

## 9. Create a Sandbox Template

A sandbox template saves the image and environment settings you want every run to use.

Set a friendly template name:

```bash
TEMPLATE_NAME=github-agent
```

Create the template:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" sandbox template create "$TEMPLATE_NAME" \
  --image quay.io/redhat-services-prod/hcm-eng-prod-tenant/hypershell-main/hypershell-agent-runtime-main \
  --env ANTHROPIC_BASE_URL=https://api.enmaas.devshift.net \
  --env ANTHROPIC_DEFAULT_MODEL=rits/zai-org/glm-5-3 \
  --env CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1 \
  --env CLAUDE_CODE_SIMPLE=1
```


## 10. Add the Automation Script

Now we will add a small script to your GitHub repository. This script does four things:

1. Authenticates to HyperShell with the service account
2. Creates a sandbox from your template
3. Clones your repository and runs a prompt
4. Downloads the result and deletes the sandbox

Save [.hypershell/run-agent.sh](https://raw.githubusercontent.com/kdoberst/hypershell-config-files/refs/heads/main/.hypershell/run-agent.sh) in your repository:

```bash
.hypershell/run-agent.sh
```

Right now the script looks at the hypershell repo and downloads a summary.  Modify the script to whatever you need.

Make the script executable:

```bash
chmod +x .hypershell/run-agent.sh
```

## 11. Add the GitHub Actions Workflow

Save [.github/workflows/hypershell-agent.yaml](https://raw.githubusercontent.com/kdoberst/hypershell-config-files/refs/heads/main/.github/workflows/hypershell-agent.yml) in your repository:
```yaml
.github/workflows/hypershell-agent.yml
```

This workflow runs only when you manually trigger it from the GitHub Actions UI. After the basic flow works, you can add a schedule.



## 12. Add Your GitHub Actions Secrets

From your repository root, set the required secrets with the GitHub CLI:

```bash
gh secret set OPENSHELL_OIDC_CLIENT_ID --body "$OIDC_CLIENT_ID"
gh secret set OPENSHELL_OIDC_CLIENT_SECRET --body "$OPENSHELL_OIDC_CLIENT_SECRET"
gh secret set OIDC_ISSUER --body "$OIDC_ISSUER"
gh secret set OIDC_AUDIENCE --body "$OIDC_AUDIENCE"
gh secret set GATEWAY_URL --body "$GATEWAY_URL"
```

You do not need to store the EnMaaS key or GitHub token here because HyperShell already stores them as providers.

## 13. Run Your Workflow

Trigger the workflow from the command line:

```bash
gh workflow run hypershell-agent.yml --ref main
```

Replace `main` with the branch that contains your workflow if needed.

Find the latest run and save its ID:

```bash
RUN_ID="$(gh run list --workflow hypershell-agent.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Watch it finish:

```bash
gh run watch "$RUN_ID" --exit-status
```

GitHub Actions will:

* Authenticate to HyperShell with your service account
* Create a fresh sandbox
* Clone your repository inside the sandbox
* Run the prompt
* Download `output/result.md`
* Delete the sandbox
* Upload the result as an Actions artifact

## 14. Retrieve Your Result

Download the artifact:

```bash
gh run download "$RUN_ID" --name agent-output --dir ./output
```

Open the result:

```bash
open ./output/result.md
```

On Linux, use `xdg-open` instead of `open`.

Congratulations! You have just used the GitHub CLI to run a prompt in a secure, disposable HyperShell sandbox.

## Summary

This tutorial covers creating a sandbox from a script and using GitHub Actions to schedule and control runs. Sandboxes are completely disposable, and a new one is created automatically on each run.

The gateway, service account, profiles, providers, and template are reusable. Once this flow works, you can change the prompt, clone a different repository, or add a schedule without starting over.


