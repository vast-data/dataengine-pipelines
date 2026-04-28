import gc
import math
import os
import tempfile
import urllib.parse

import boto3


def init(ctx):
    ctx.logger.info("Init: video segmenter")

    secrets = ctx.secrets.get("secrets", {})
    s3_access_key = secrets.get("S3_ACCESS_KEY", "")
    s3_secret_key = secrets.get("S3_SECRET_KEY", "")

    ctx.s3_mock = os.environ.get("S3_MOCK", "false").lower() == "true"
    ctx.logger.info(f"S3_MOCK={ctx.s3_mock}")

    if not ctx.s3_mock:
        s3_endpoint = os.environ.get("S3_ENDPOINT_URL", "")
        s3_region = os.environ.get("S3_REGION", "us-east-1")
        if not s3_access_key or not s3_secret_key:
            raise ValueError("Missing required secrets: S3_ACCESS_KEY, S3_SECRET_KEY")
        if not s3_endpoint:
            raise ValueError("Missing S3_ENDPOINT_URL")
        ctx.s3_client = boto3.client(
            "s3",
            use_ssl=False,
            endpoint_url=s3_endpoint,
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
            region_name=s3_region,
            config=boto3.session.Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )
        ctx.logger.info("S3 client initialized")
    else:
        ctx.s3_client = None

    ctx.segment_duration = int(os.environ.get("SEGMENT_DURATION", "5"))
    ctx.output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    ctx.logger.info(f"Segment duration: {ctx.segment_duration}s")
    if not ctx.output_bucket:
        ctx.logger.warning("OUTPUT_BUCKET not set — segments will be written to the source bucket")


def handler(ctx, event):
    ctx.logger.info(f"Handler invoked | event.data={event.data}")

    records = event.data.get("Records") or event.data.get("data", {}).get("Records", [])
    if not records:
        ctx.logger.warning("No Records found in event")
        return {"status": "error", "reason": "No Records in event"}

    bucket = records[0]["s3"]["bucket"]["name"]
    key = urllib.parse.unquote(records[0]["s3"]["object"]["key"])
    filename = os.path.basename(key)
    ctx.logger.info(f"Bucket: {bucket} | Key: {key}")

    # Only process .mp4 files; skip segments we already created to prevent re-processing
    # our own output when OUTPUT_BUCKET is the same as the source bucket.
    if not key.lower().endswith(".mp4"):
        ctx.logger.info(f"Skipping non-mp4 file: {key}")
        return {"status": "skipped", "reason": f"Not a .mp4 file: {key}"}

    if "_segment_" in key.lower():
        ctx.logger.info(f"Skipping already-segmented file: {key}")
        return {"status": "skipped", "reason": f"Already a segment: {key}"}

    output_bucket = ctx.output_bucket or bucket

    if ctx.s3_mock:
        sample_path = os.path.join(os.path.dirname(__file__), "sample.mp4")
        with open(sample_path, "rb") as f:
            video_bytes = f.read()
        ctx.logger.info(f"S3_MOCK=true — loaded sample.mp4 ({len(video_bytes):,} bytes)")
    else:
        ctx.logger.info(f"Downloading s3://{bucket}/{key}")
        response = ctx.s3_client.get_object(Bucket=bucket, Key=key)
        video_bytes = response["Body"].read()
        ctx.logger.info(f"Downloaded {len(video_bytes):,} bytes")

    segment_keys = segment_and_upload(ctx, video_bytes, filename, output_bucket)

    # TODO 4: Return a result dict with:
    # status, source_bucket, source_key, output_bucket, segment_keys, segment_count, segment_duration


def segment_and_upload(ctx, video_bytes, filename, output_bucket):
    """Slice video into segments and save each one.

    If ctx.s3_mock is True, write segments to ./segments/ locally for review.
    Otherwise upload each segment to S3 under segments/<name>_segment_NNN_of_NNN.mp4.
    Returns a list of segment keys (local paths or S3 keys).
    """
    from moviepy.editor import VideoFileClip

    base = os.path.splitext(filename)[0]
    segment_keys = []

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_in:
        tmp_in.write(video_bytes)
        tmp_in_path = tmp_in.name

    try:
        clip = VideoFileClip(tmp_in_path)
        total_duration = clip.duration
        total_segments = math.ceil(total_duration / ctx.segment_duration)
        ctx.logger.info(f"Video: {total_duration:.2f}s -> {total_segments} x {ctx.segment_duration}s segments")

        for i in range(total_segments):
            start = i * ctx.segment_duration
            end = min(start + ctx.segment_duration, total_duration)
            segment_key = f"segments/{base}_segment_{i+1:03d}_of_{total_segments:03d}.mp4"
            ctx.logger.info(f"Segment {i+1}/{total_segments}: {start:.1f}s-{end:.1f}s")

            sub = clip.subclip(start, end)
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_out:
                tmp_out_path = tmp_out.name
            sub.write_videofile(tmp_out_path, codec="libx264", audio=False, logger=None)
            sub.close()

            with open(tmp_out_path, "rb") as f:
                segment_bytes = f.read()
            os.unlink(tmp_out_path)
            gc.collect()

            if ctx.s3_mock:
                os.makedirs("segments", exist_ok=True)
                local_path = os.path.join("segments", os.path.basename(segment_key))
                with open(local_path, "wb") as f:
                    f.write(segment_bytes)
                ctx.logger.info(f"Saved locally: {local_path}")
            else:
                ctx.s3_client.put_object(
                    Bucket=output_bucket,
                    Key=segment_key,
                    Body=segment_bytes,
                    Metadata={
                        "original-video": filename,
                        "segment-number": str(i + 1),
                        "total-segments": str(total_segments),
                        "segment-duration": str(ctx.segment_duration),
                    },
                )
                ctx.logger.info(f"Uploaded: {segment_key}")

            segment_keys.append(segment_key)

        clip.close()
        gc.collect()

    finally:
        if os.path.exists(tmp_in_path):
            os.unlink(tmp_in_path)

    return segment_keys
