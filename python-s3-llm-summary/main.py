import os
import urllib.parse
import boto3
from openai import OpenAI

EXPECTED_ENVS = [
    'S3_MOCK', 'S3_ENDPOINT_URL', 'S3_REGION',
    'LLM_MOCK', 'LLM_ENDPOINT', 'MODEL_NAME', 'MAX_TOKENS',
]

def init(ctx):
    ctx.logger.info("🚀 Init")
    for key in EXPECTED_ENVS:
        val = os.environ.get(key)
        ctx.logger.info(f"ℹ️ {key}={val if val is not None else 'NOT SET'}")

    # Load secrets
    secrets = ctx.secrets.get("secrets", {})
    s3_access_key = secrets.get("S3_ACCESS_KEY", "")
    s3_secret_key = secrets.get("S3_SECRET_KEY", "")
    llm_api_key   = secrets.get("LLM_API_KEY", "")
    ctx.logger.info(f"ℹ️ S3_ACCESS_KEY={'set' if s3_access_key else 'NOT SET'}")
    ctx.logger.info(f"ℹ️ S3_SECRET_KEY={'set' if s3_secret_key else 'NOT SET'}")
    ctx.logger.info(f"ℹ️ LLM_API_KEY={'set' if secrets.get('LLM_API_KEY') else 'NOT SET'}")

    # S3 client
    s3_mock = os.environ.get('S3_MOCK', 'false').lower() == 'true'
    ctx.logger.info(f"ℹ️ S3_MOCK={s3_mock}")
    ctx.s3_mock = s3_mock

    if not s3_mock:
        s3_endpoint = os.environ.get('S3_ENDPOINT_URL')
        s3_region = os.environ.get('S3_REGION')
        ctx.logger.info(f"ℹ️ S3_ENDPOINT_URL={s3_endpoint}")
        ctx.logger.info(f"ℹ️ S3_REGION={s3_region}")
        if not s3_access_key or not s3_secret_key:
            ctx.logger.error("⚠️ S3_ACCESS_KEY or S3_SECRET_KEY missing from secrets")
            raise ValueError("Missing required S3 secrets")
        if not s3_endpoint:
            ctx.logger.error("⚠️ S3_ENDPOINT_URL missing")
            raise ValueError("Missing S3_ENDPOINT_URL")
        ctx.s3_client = boto3.client(
            's3',
            use_ssl=False,
            endpoint_url=s3_endpoint,
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
            region_name=s3_region,
            config=boto3.session.Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'}
            )
        )
        ctx.logger.info("✅ S3 client initialized")
    else:
        ctx.s3_client = None
        ctx.logger.info("ℹ️ S3_MOCK=true, skipping S3 client init")

    # LLM client
    llm_mock = os.environ.get('LLM_MOCK', 'true').lower() == 'true'
    ctx.logger.info(f"ℹ️ LLM_MOCK={llm_mock}")

    if not llm_mock:
        endpoint = os.environ.get('LLM_ENDPOINT', '')
        if not endpoint:
            ctx.logger.error("⚠️ LLM_ENDPOINT missing")
            raise ValueError("Missing LLM_ENDPOINT")
        ctx.llm_client = OpenAI(base_url=endpoint, api_key=llm_api_key)
        ctx.logger.info(f"✅ LLM client initialized → {endpoint}")
    else:
        ctx.llm_client = None
        ctx.logger.info("ℹ️ LLM_MOCK=true, skipping LLM client init")

def handler(ctx, event):
    ctx.logger.info("ℹ️ Handler invoked")
    ctx.logger.info(f"ℹ️ event.data={event.data}")

    # Parse S3 event
    records = event.data.get('Records') or event.data.get('data', {}).get('Records', [])
    if not records:
        ctx.logger.warning("⚠️ No Records found in event")
        return "Error: No Records found in event data"

    s3_bucket = records[0]['s3']['bucket']['name']
    s3_key = urllib.parse.unquote(records[0]['s3']['object']['key'])
    ctx.logger.info(f"📦 Bucket: {s3_bucket}")
    ctx.logger.info(f"📄 Key: {s3_key}")

    # Fetch file from S3
    if ctx.s3_mock:
        sample_path = os.path.join(os.path.dirname(__file__), "sample.txt")
        content = open(sample_path).read()
        ctx.logger.info("ℹ️ S3_MOCK=true — using sample.txt as placeholder content")
    else:
        ctx.logger.info("⬇️ Fetching file from S3...")
        try:
            response = ctx.s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
            content = response['Body'].read().decode('utf-8')
            ctx.logger.info(f"✅ File fetched — size: {response['ContentLength']} bytes, type: {response['ContentType']}")
        except Exception as e:
            ctx.logger.error(f"⚠️ Error fetching file: {e}")
            return f"Error fetching file: {e}"

    ctx.logger.info("🤖 Calling LLM for summary...")
    summary = llm_summary(ctx, content)
    ctx.logger.info(f"✅ Summary: {summary}")

    return {"bucket": s3_bucket, "key": s3_key, "summary": summary}

def llm_summary(ctx, content):
    if ctx.llm_client is None:
        ctx.logger.info("ℹ️ LLM_MOCK=true — returning placeholder summary")
        return "[mock] This is a placeholder summary for local testing without an LLM."

    model = os.environ.get("MODEL_NAME", "gpt-4o-mini")
    max_tokens = int(os.environ.get("MAX_TOKENS", "512"))
    ctx.logger.info(f"ℹ️ Model: {model}, MaxTokens: {max_tokens}")

    query = f"Summarize in 1-2 sentences:\n{content}"
    try:
        completion = ctx.llm_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": query}],
            max_tokens=max_tokens,
            stream=True,
        )
        out = "".join(
            chunk.choices[0].delta.content
            for chunk in completion
            if chunk.choices[0].delta.content
        )
        return out.split("</think>")[-1].strip()
    except Exception as e:
        ctx.logger.error(f"⚠️ LLM call failed: {e}")
        return f"Error: LLM call failed — {e}"
