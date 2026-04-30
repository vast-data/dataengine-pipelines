# python-s3-segment-video

## Overview

An S3-triggered pipeline that downloads an uploaded `.mp4` video, slices it into fixed-duration segments using moviepy, and uploads the segments back to S3. The structured return value (`segment_keys`) is designed to feed into a downstream VLM function.

| Field | Value |
|---|---|
| **Trigger** | S3 Create Event |
| **Runtime** | Python 3.12.12 |
| **Status** | Complete |

> **Do not commit video files to this repository.** All video formats are excluded via `.gitignore`. Download sample data locally — see [Local Development](#local-development).

## Prerequisites

- Access to a VAST DataEngine tenant and container registry (below as `<registry-host>`)
- `vastde` CLI installed and configured, see [DEVELOPMENT.md](../DEVELOPMENT.md)
  - run `vastde --version` to check installation
  - run `vastde functions list` to check that you have DataEngine access
- An S3 bucket to watch for `.mp4` uploads and an output bucket for segments

## Project Structure

    |- main.py                # Function handlers — init, handler, segment_and_upload
    |- requirements.txt       # Python dependencies
    |- Aptfile                # System packages
    |- customDeps             # Custom dependencies such as private common libraries
    |- config.example.yaml    # Environment variable template, copy to config.yaml and fill in values
    |- pipeline-config.yaml   # Pipeline definition (trigger → function wiring)
    |- README.md              # This file
    |- cloudevent.json        # Sample CloudEvent for local testing with `vastde functions invoke`
    |- secrets.example.yaml   # Secrets template, copy to secrets.yaml and fill in values

## Configuration

Copy `config.example.yaml` to `config.yaml` and fill in your values:

```bash
cp config.example.yaml config.yaml
```

Never commit `config.yaml`. It is already included in `.gitignore`.

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `S3_MOCK` | No | Set to `true` to use local `sample.mp4` instead of real S3 (default: `false`) |
| `S3_ENDPOINT_URL` | When `S3_MOCK=false` | S3 endpoint URL (e.g. `http://s3.your-endpoint.com`) |
| `S3_REGION` | No | S3 region (e.g. `us-east-1`) |
| `SEGMENT_DURATION` | No | Segment length in seconds (default: `5`) |
| `OUTPUT_BUCKET` | No | Bucket to write segments to — defaults to the source bucket if not set |

### Secrets

Copy `secrets.example.yaml` to `secrets.yaml` and fill in your values:

```bash
cp secrets.example.yaml secrets.yaml
```

Never commit `secrets.yaml`. It is already included in `.gitignore`.

| Secret | Required | Description |
|---|---|---|
| `S3_ACCESS_KEY` | When `S3_MOCK=false` | S3 access key |
| `S3_SECRET_KEY` | When `S3_MOCK=false` | S3 secret key |

## Run Function on DataEngine

Follow these steps to deploy and run the function on DataEngine. For detailed instructions, refer to the [DataEngine Documentation](https://kb.vastdata.com/documentation/docs/version-54-3).

> **Note:** Commands use `$USER` (`echo $USER` value) as a prefix for resource names (e.g. `$USER-s3-segment-video`). This avoids naming collisions when multiple users are deploying to a shared tenant.

### 1. Build Function

Build the function image, then register it as a function in DataEngine:

```bash
cd python-s3-segment-video
vastde functions build $USER-s3-segment-video
```

Push the image to your container registry:

```bash
docker tag $USER-s3-segment-video:latest <registry-host>/<registry-user>/$USER-s3-segment-video:<version>
docker push <registry-host>/<registry-user>/$USER-s3-segment-video:<version>
```

Create the function on DataEngine:

```bash
vastde functions create \
  --name $USER-s3-segment-video \
  --container-registry <registry-name-on-vms> \
  --artifact-source <registry-user>/$USER-s3-segment-video \
  --image-tag <version>
```

### 2. Set up Trigger

Navigate to the DataEngine UI and click `Triggers` + `Create Trigger`. Fill in the following fields:

| Field | Example value | Notes |
|---|---|---|
| **Name** | `$USER-s3-segment-video-trigger` | Must match the trigger name in `pipeline-config.yaml` |
| **Trigger Type** | `Element` | |
| **Source View** | select your S3 bucket | The bucket to watch for `.mp4` uploads |
| **Element Type** | `Element Created` | |

Verify via CLI:

```bash
vastde triggers list
```

### 3. Deploy Pipeline

Navigate to the DataEngine UI and click `Pipelines` + `Create Pipeline`. Fill in the following fields:

| Field | Example value | Notes |
|---|---|---|
| **Name** | `$USER-s3-segment-video-pipeline` | |
| **Function** | `$USER-s3-segment-video` | Select the function created in step 1 |
| **Trigger** | `$USER-s3-segment-video-trigger` | Select the trigger created in step 2 |

Under **Environment Variables**, add:

| Key | Value |
|---|---|
| `S3_ENDPOINT_URL` | your S3 endpoint |
| `S3_REGION` | your S3 region |
| `SEGMENT_DURATION` | `5` |
| `OUTPUT_BUCKET` | your output bucket name |

Under **Secrets**, add:

| Key | Value |
|---|---|
| `S3_ACCESS_KEY` | your S3 access key |
| `S3_SECRET_KEY` | your S3 secret key |

Deploy the pipeline, then verify it is ready:

```bash
vastde pipelines list
```

### 4. Test Pipeline with S3 Upload

Upload an `.mp4` file to your source bucket to trigger the pipeline:

```bash
s3cmd put ./sample.mp4 s3://<your-bucket>/sample.mp4
```

Check the output:

```bash
vastde logs tail $USER-s3-segment-video-pipeline --function $USER-s3-segment-video --since 1h
```

Expected output:

```
[INFO] Downloading s3://<your-bucket>/sample.mp4
[INFO] Video: 596.46s -> 120 x 5s segments
[INFO] Result: {'status': 'success', 'source_bucket': '...', 'segment_count': 120, ...}
```

## Local Development

### Sample Video

This pipeline requires a `sample.mp4` in the function directory for mock mode (`S3_MOCK=true`). Source any `.mp4` file and place it in the pipeline directory before building.

> **Note:** `sample.mp4` must be present before running `vastde functions build` — it is baked into the Docker image at build time. If you update the file, run `docker rmi <image>` and rebuild.

### Build

```bash
vastde functions build $USER-s3-segment-video
```

### Run Locally

```bash
vastde functions localrun $USER-s3-segment-video -c config.yaml
```

### Invoke

```bash
vastde functions invoke --event ./cloudevent.json --url http://localhost:8080/
```

## Resources

- [DEVELOPMENT.md](../DEVELOPMENT.md): local setup and CLI workflow
- [CONTRIBUTING.md](../CONTRIBUTING.md): how to contribute
- [DataEngine Docs](https://kb.vastdata.com/documentation/docs/version-54-3)
- [DataEngine CLI](https://github.com/vast-data/dataengine-cli)
- [VAST Community](https://community.vastdata.com/)
- [VAST Developers](https://www.vastdata.com/developers)
