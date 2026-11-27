# A Beginner’s Guide to HyperShell: Running Prompts from the CLI

You likely have a prompt that might take a while to finish, needs to run overnight, or you simply do not want to tie up your laptop's resources. That is exactly what HyperShell is for! This tutorial will show you how to securely run OpenShell sandboxes in the cloud using only the command line.

We will walk through every step together and explain exactly *what* is happening and *why*, so you can feel confident about what you are doing.

In this specific walkthrough, we will run a simple agent skill that summarizes open GitHub pull requests, GitHub issues, and Jira items. We will connect to EnMaaS using Claude. This tutorial assumes you are a Red Hat employee with access to Red Hat's Jira instance.

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


## 2. Log In to HyperShell

`hsctl` talks to the HyperShell control plane. It is the tool you will use to create your gateway. Use the API server URL below, not the HyperShell web app URL and not a gateway endpoint.

Log in with:

```bash
hsctl login --url https://api.hyp2.infra.hypershell.app/

```

This opens a browser and saves your HyperShell credentials locally.


## 3. Create Your Gateway

A gateway is your dedicated home base in HyperShell. It owns your workspaces, profiles, providers, templates, and sandboxes.

Set a friendly gateway name:

```bash
GATEWAY_NAME=simple-cli
WORKSPACE=default
```

This tutorial uses the `default` workspace. If you later create another workspace, change `WORKSPACE` to that name.

Create the gateway on the public IBM Cloud:

```bash
hsctl create gateway \
  --name "$GATEWAY_NAME" \
  --placement-selector network/public \
  --placement-selector provider/ibm
```

Then capture the gateway ID. If you have `jq`, you can copy and paste:

```bash
GATEWAY_ID="$(hsctl list gateways -o json | jq -r --arg name "$GATEWAY_NAME" '.items[] | select(.name == $name) | .id')"
```

If you do not want to install `jq`, run:

```bash
hsctl list gateways
```

Copy the ID for your gateway and set it manually:

```bash
GATEWAY_ID="<your-gateway-id>"
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

Copy the `openshell gateway add ...` command (step 1) from that output and run it in your terminal.

Then log in to the gateway:

```bash
openshell gateway login "$GATEWAY_NAME"
```


## 5. Import Profiles

Profiles are reusable blueprints. They tell HyperShell which external systems a sandbox may reach and which binaries are allowed to reach them.

We need three profiles:

* EnMaaS, for the model
* GitHub, for pull requests and issues
* Jira, for Jira items

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

Import the Jira profile:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" profile import \
  --url https://raw.githubusercontent.com/kdoberst/hypershell-config-files/refs/heads/main/profiles/jira.yaml
```

Confirm the profiles are available:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" profile list
```

These profiles carry the network rules the sandbox needs. You do not need a separate sandbox policy file for this walkthrough.

## 6. Create Providers

If profiles are blueprints, providers are secure vaults. A provider stores the real credentials that a profile references.

Export your secrets as environment variables:

```bash
export ANTHROPIC_API_KEY="<your-enmaas-key>"
export GITHUB_TOKEN="<your-github-token>"
export JIRA_API_TOKEN="<your-jira-token>"
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

Create the Jira provider:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" provider create \
  --name jira \
  --type jira \
  --credential JIRA_API_TOKEN
```

These providers can stay in your workspace and be reused by future sandboxes.

## 7. Create a Sandbox Template

A sandbox template saves the image and environment settings you want every run to use.

Set a friendly template name and your email (replace `<you>`)

```bash

TEMPLATE_NAME=simple-agent
JIRA_EMAIL=<you>@redhat.com

```

Create the template:
```bash

openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" sandbox template create "$TEMPLATE_NAME" \
  --image quay.io/redhat-services-prod/hcm-eng-prod-tenant/hypershell-main/hypershell-agent-runtime-main \
  --env ANTHROPIC_BASE_URL=https://api.enmaas.devshift.net \
  --env ANTHROPIC_DEFAULT_MODEL=rits/zai-org/glm-5-3 \
  --env CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1 \
  --env CLAUDE_CODE_SIMPLE=1 \
  --env JIRA_SITE_URL=https://redhat.atlassian.net \
  --env JIRA_BASE_URL=https://redhat.atlassian.net \
  --env JIRA_EMAIL=$JIRA_EMAIL
```

The Jira API token and email are supplied by the Jira provider, so you should not put them in the template.

## 8. Spin Up Your Sandbox

Now you can create the sandbox that will run the agent.

Set a short sandbox name:

```bash
SANDBOX_NAME="hs-$(date +%m%d%H%M%S)"
```

Create the sandbox:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" sandbox create \
  --name "$SANDBOX_NAME" \
  --template "$TEMPLATE_NAME" \
  --provider enmaas-claude \
  --provider github \
  --provider jira \
  --no-auto-providers \
  --detach \
  -- sleep infinity
```

The sandbox starts from your template and attaches the three providers you created. Their profiles automatically contribute the network rules the sandbox needs.

## 9. Upload the Skill

We are using one self-contained skill: it fetches GitHub and Jira items and writes the summary file.

Download and expand the sample skill from:

```text
https://github.com/kdoberst/hypershell-config-files/tree/main/sample-skills
```

You should end up with a local directory named `work-summary`.

Upload it into the sandbox:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" sandbox upload \
  "$SANDBOX_NAME" \
  ./work-summary \
  /sandbox/.claude/skills/work-summary
```

## 10. Run Your Skill

Run the skill from your terminal:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" sandbox exec \
  -n "$SANDBOX_NAME" \
  -- bash -lc 'claude -p "Run the work-summary skill"'
```

Claude will run inside the sandbox, use the attached providers, and write the result to:

```text
/sandbox/output/work-summary.md
```

## 11. Download Your Result

When the prompt finishes, download the result:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" sandbox download \
  "$SANDBOX_NAME" \
  /sandbox/output/work-summary.md \
  .
```

You should now see `work-summary.md` in your current directory.

## 12. Clean Up

Sandboxes are intended to be disposable. When you are finished, delete this one:

```bash
openshell -g "$GATEWAY_NAME" --workspace "$WORKSPACE" sandbox delete "$SANDBOX_NAME"
```

Keep the gateway, profiles, providers, and template. They are reusable.

## Summary

This tutorial covers creating a simple sandbox and running a skill.  Sandboxes are intended to run a single prompt or script and then be deleted.  By creating the gateway and template, making additional sandboxes in the future - all you have to is start with Step 8 Spin Up Your Sandbox
