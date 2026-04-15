## Overview

A hello world function triggered on a S3 created event. Logs a greeting on initialization and the trigger event on each invocation.

| Field | Value |
|---|---|
| **Trigger** | S3 Create Event  |
| **Runtime** | Python 3.12.12 |
| **Status** | Complete |

## Prerequisites

- Access to a VAST DataEngine tenant and container registry (below as `<registry-host>`)
- `vastde` CLI installed and configured, see [DEVELOPMENT.md](../DEVELOPMENT.md)
  - run `vastde --version` to check installation
  - run `vastde functions list` to check that you have DataEngine access

## Project Structure
    |- main.py               # Your function handlers (init and handler)
    |- requirements.txt      # Python dependencies
    |- Aptfile               # System packages
    |- customDeps            # custom dependencies such as private common libraries
    |- config.example.yaml   # Environment variable template, copy to config.yaml and fill in values
    |- pipeline-config.yaml  # Pipeline definition (trigger → function wiring)
    |- README.md             # This file
    |- test.md               # Example file to upload via Virtual Machine (instructions below)

## (Optional) Configuration

Copy `config.example.yaml` to `config.yaml` and fill in your values:

```bash
cp config.example.yaml config.yaml
```

### (Optional) Environment Variables

Never commit `config.yaml`. It is already included in `.gitignore`.

## Run Function on DataEngine

Follow these steps to deploy and run the function on DataEngine. For detailed instructions, refer to the [DataEngine Documentation](https://kb.vastdata.com/documentation/docs/version-54-3).

Instructions are given using the `vastde` CLI and DataEngine UI.

> **Note:** Commands use `$USER` (`echo $USER` value) as a prefix for resource names (e.g. `$USER-s3-hello-world`). This avoids naming collisions when multiple users are deploying to a shared tenant. Also, consider using `${USER//./-}` instead of $USER to swap `.` with `-` for readability.

### 1. Build Function

Build the function image, then register it as a function in DataEngine:

```bash
cd python-s3-hello-world
vastde functions build $USER-s3-hello-world
```

```bash
# vastde functions build output
Detected language: python
Validating Python version 3.12.*...
Python version 3.12.* resolved to 3.12.12
Building $USER-s3-hello-world:latest
App Path: .../python-s3-hello-world
Handlers File: main.py
Build log: .../python-s3-hello-world/build.log
2026/03/18 14:22:18 [Started] Python Builder: $USER-s3-hello-world:latest
2026/03/18 14:22:34 [Completed] Python Builder: $USER-s3-hello-world:latest
Build completed: $USER-s3-hello-world:latest
Build log saved to: .../python-s3-hello-world/build.log
```

Push the image to your container registry configured on your DataEngine tenant (search for `Container Registries` in VMS):

```bash
docker tag $USER-s3-hello-world:latest <registry-host>/<registry-user>/$USER-s3-hello-world:<version>
docker push <registry-host>/<registry-user>/$USER-s3-hello-world:<version>
```

Create the function on DataEngine:
```bash
vastde functions create \
 --name $USER-s3-hello-world \
 --container-registry <registry-name-on-vms> \
 --artifact-source <registry-user>/$USER-s3-hello-world  \
 --image-tag <version>
```

```bash
# vastde functions create output
Function created: $USER-s3-hello-world
Name: $USER-s3-hello-world
Tags: []
GUID: <guid>
Owner: [id: <id>, id-type: vid]
Created At: 2026-03-18T18:50:47Z
Updated At: 2026-03-18T18:50:47Z
VRN: vast:dataengine:functions:$USER-s3-hello-world
Last Revision: 1
```

List the available functions: `vastde functions list`:

```bash
# vastde functions list output
Function Name              Description                          Guid                                    Updated at         
---------------------------------------------------------------------------------------------------------------------------
$USER-s3-hello-world                                           ca87e704-2501-4bc2-8ebe-aeba3ca7ed3f    2026-04-08 15:03 
```

### 2. Set up Trigger

To create the trigger, navigate to the DataEngine UI and click on `Triggers` + `Create Trigger`:

![alt text](set-up-trigger.png)

Fill in the following fields:

| Field | Example value | Notes |
|---|---|---|
| **Name** | `$USER-s3-trigger` | Replace $USER with `echo $USER` value. Must match the trigger name in `pipeline-config.yaml`. The pipeline create step will fail if the trigger does not exist or the name does not match |
| **Trigger Type** | `Element` | |
| **Source View** | `select s3 bucket` | We will use `s3cmd` to upload to the s3 bucket |
| **Element Type** | `Element Created` | |
| **Description** | `s3 element created event` | Optional |
<!-- | **Cron Expression** | `0 0/5 * ? * * *` | Runs every 5 minutes | -->

> **Note:** For `Source View`, ensure you have access to the S3 bucket for adding files to trigger pipeline.

Afterwards, you can view the trigger via CLI:

```bash
vastde triggers list
```

```bash
# vastde triggers list output
Trigger Name               Status        Type        Description      GUID                        Updated at
------------------------------------------------------------------------------------------------------------------
$USER-s3-trigger       Ready         0xc0006...                   4d32fd72-7961-4b00-940b...  2026-03-29 21:23
schedule-20m-trigger       Ready         0xc0004...  Schedule tri...  6a9f2b3a-605d-4593-a90e...  2026-03-29 21:22
```

### 3. Deploy Pipeline

Create a pipeline connecting the trigger to the function using `pipeline-config.yaml`. 

> Before running, ensure the resource names in `pipeline-config.yaml` are updated (i.e. replace `$USER`):

```bash
vastde pipelines create --config pipeline-config.yaml
```

```bash
# vastde pipelines create output
Pipeline created: $USER-s3-hello-world-pipeline
Name: $USER-s3-hello-world-pipeline
Description: A sample pipeline to print hello world on a s3 element created event
Tags: [element-created]
GUID: df31058f-9e34-48f0-97ea-7222138e5bff
Owner: [id: 477, id-type: vid]
Created At: 2026-03-29T21:51:00Z
Updated At: 2026-03-29T21:51:00Z
VRN: vast:dataengine:pipelines:$USER-s3-hello-world-pipeline
```

You can deploy the pipeline via UI or CLI:

```bash
vastde pipelines deploy $USER-s3-hello-world-pipeline
```

```bash
# vastde pipelines deploy output
Pipeline deployed successfully
```

After the pipeline is deployed, tail the logs to verify the function is being invoked:

```bash
vastde logs tail $USER-s3-hello-world-pipeline --function $USER-s3-hello-world --since 1h
```


```bash
# vastde logs tail output
2026-04-08 11:27:58.01 [$USER-s3-hell...] [INFO]  [user] Initialized... Hello, World!```
```

### 4. Test Pipeline with S3 file upload
 
Confirm network access to the S3 bucket via `ping <S3 Endpoint>`.

Run the following command to upload the example file to your S3 bucket to trigger the pipeline.

```bash
s3cmd put ./test.md s3://<your-bucket>/test.md
upload: './test.md' -> 's3://<your-bucket>/test.md'  [1 of 1]
 15 of 15   100% in    0s  1548.79 B/s  done
```

Check the pipeline output again:

```bash
vastde logs tail $USER-s3-hello-world-pipeline --function $USER-s3-hello-world --since 1h
```

```bash
#vastde logs tail output
2026-04-08 15:27:58.01 [$USER-s3-hell...] [INFO]  [user] Initialized... Hello, World!
2026-04-08 15:41:29.67 [$USER-s3-hell...] [INFO]  [user] Handler {'attributes': {'source': 'vastdata.com:$USER-s3-trigger.b45a6820-410c-457a-ac1b-035a102b5d05', 'id': '1004356627333135', 'type': 'vastdata.com:Element.ElementCreated', 'specversion': '1.0', 'time': '2026-04-08T15:41:29.591955+00:00', 'subject': 'vast-broker-engine-broker.main', 'datacontenttype': 'application/json', 'dataschema': None, 'elementhandle': '8025198034623744117', 'elementpath': 's3-bucket-name/test.md', 'elementsourcetype': 'vast:s3', 'knativekafkaoffset': '135498', 'knativekafkapartition': '0'}, 'data': {'Records': [{'eventVersion': '2.2', 'eventSource': 'vast:s3', 'awsRegion': 'selab-var-201', 'eventTime': '2026-04-08T15:41:29.591955Z', 'eventName': 'ObjectCreated:Put', 'userIdentity': {'principalId': 'principleId'}, 'requestParameters': {'sourceIPAddress': '172.200.11.10'}, 'responseElements': {'x-amz-request-id': '0x391710286a372', 'x-amz-id-2': '0x391710286a372'}, 's3': {'s3SchemaVersion': '1.0', 'configurationId': '$USER-s3-trigger.b45a6820-410c-457a-ac1b-035a102b5d05', 'bucket': {'name': 's3-bucket-name', 'ownerIdentity': {'principalId': 'principleId'}, 'arn': 'arn:aws:s3:::s3-bucket-name'}, 'object': {'key': 'test.md', 'size': 15, 'eTag': '1d6155b60405bab055527913efd734a7', 'sequencer': '009f00000000000f42fd'}}}]}}
```

## Local Development

### Build

```bash
vastde functions build $USER-s3-hello-world
```

### Run locally

```bash
vastde functions localrun $USER-s3-hello-world -c config.yaml
```

### Invoke

```bash
vastde functions invoke --generate-event --url http://localhost:8080/
```

## Resources

- [DEVELOPMENT.md](../DEVELOPMENT.md): local setup and CLI workflow
- [CONTRIBUTING.md](../CONTRIBUTING.md): how to contribute
- [DataEngine Docs](https://kb.vastdata.com/documentation/docs/version-54-3)
- [DataEngine CLI](https://github.com/vast-data/dataengine-cli)
- [VAST Community](https://community.vastdata.com/)
- [VAST Developers](https://www.vastdata.com/developers)