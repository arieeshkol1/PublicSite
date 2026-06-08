"""AI Model Router - unified interface for multiple LLM providers."""
from __future__ import annotations

import json
import logging
import os

import boto3

from .models import ModelConfig, ExecutionPayload
from .constants import MEMBERS_TABLE

logger = logging.getLogger(__name__)

# Global default model configuration
_DEFAULT_MODEL_CONFIG = ModelConfig(
    provider="bedrock",
    model_id="us.amazon.nova-2-lite-v1:0",
    region=os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "us-east-1")),
    api_key_secret_arn=None,
    max_tokens=4096,
    temperature=0.1,
)


def get_model_config(member_email: str) -> ModelConfig:
    """Resolve model configuration: tenant override > global default."""
    try:
        dynamodb = boto3.resource("dynamodb")
        members_table = dynamodb.Table(MEMBERS_TABLE)
        response = members_table.get_item(
            Key={"email": member_email},
            ProjectionExpression="aiModelConfig",
        )
        item = response.get("Item", {})
        config_data = item.get("aiModelConfig")

        if config_data and isinstance(config_data, dict):
            return ModelConfig(
                provider=config_data.get("provider", _DEFAULT_MODEL_CONFIG.provider),
                model_id=config_data.get("modelId", _DEFAULT_MODEL_CONFIG.model_id),
                region=config_data.get("region", _DEFAULT_MODEL_CONFIG.region),
                api_key_secret_arn=config_data.get("apiKeySecretArn"),
                max_tokens=int(config_data.get("maxTokens", _DEFAULT_MODEL_CONFIG.max_tokens)),
                temperature=float(config_data.get("temperature", _DEFAULT_MODEL_CONFIG.temperature)),
            )
    except Exception as e:
        logger.warning(f"Failed to load tenant model config: {e}")

    return _DEFAULT_MODEL_CONFIG


def invoke_model(config: ModelConfig, payload: ExecutionPayload) -> str:
    """Invoke the AI model using the appropriate provider.

    Supports: bedrock, openai, azure-openai
    """
    provider = config.provider.lower()

    try:
        if provider == "bedrock":
            return _invoke_bedrock(config, payload)
        elif provider == "openai":
            return _invoke_openai(config, payload)
        elif provider == "azure-openai":
            return _invoke_azure_openai(config, payload)
        else:
            raise ValueError(f"Unsupported AI provider: {provider}")
    except Exception as e:
        logger.error(f"Model invocation failed ({provider}): {e}")
        raise RuntimeError(
            "AI service is temporarily unavailable. Please try again in a moment."
        ) from None


def _invoke_bedrock(config: ModelConfig, payload: ExecutionPayload) -> str:
    """Invoke AWS Bedrock model."""
    client = boto3.client("bedrock-runtime", region_name=config.region or "us-east-1")

    # Assemble full prompt
    full_prompt = f"{payload.system_prefix}\n\n{payload.available_metadata}\n\n{payload.user_query}"

    body = {
        "inputText": full_prompt,
        "textGenerationConfig": {
            "maxTokenCount": config.max_tokens,
            "temperature": config.temperature,
        },
    }

    response = client.invoke_model(
        modelId=config.model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    response_body = json.loads(response["body"].read())

    # Handle different response formats
    if "results" in response_body:
        return response_body["results"][0].get("outputText", "")
    elif "outputText" in response_body:
        return response_body["outputText"]
    elif "content" in response_body:
        # Claude format
        content = response_body["content"]
        if isinstance(content, list):
            return content[0].get("text", "")
        return str(content)

    return str(response_body)


def _invoke_openai(config: ModelConfig, payload: ExecutionPayload) -> str:
    """Invoke OpenAI GPT model."""
    import urllib.request

    api_key = _get_api_key(config.api_key_secret_arn)
    if not api_key:
        raise RuntimeError("OpenAI API key not configured")

    messages = [
        {"role": "system", "content": payload.system_prefix},
        {"role": "user", "content": f"{payload.available_metadata}\n\n{payload.user_query}"},
    ]

    body = json.dumps({
        "model": config.model_id,
        "messages": messages,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]


def _invoke_azure_openai(config: ModelConfig, payload: ExecutionPayload) -> str:
    """Invoke Azure OpenAI model."""
    import urllib.request

    api_key = _get_api_key(config.api_key_secret_arn)
    if not api_key:
        raise RuntimeError("Azure OpenAI API key not configured")

    endpoint = config.region  # For Azure, region field stores the endpoint URL
    if not endpoint:
        raise RuntimeError("Azure OpenAI endpoint not configured")

    messages = [
        {"role": "system", "content": payload.system_prefix},
        {"role": "user", "content": f"{payload.available_metadata}\n\n{payload.user_query}"},
    ]

    body = json.dumps({
        "messages": messages,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }).encode("utf-8")

    url = f"{endpoint}/openai/deployments/{config.model_id}/chat/completions?api-version=2024-02-01"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "api-key": api_key,
        },
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]


def _get_api_key(secret_arn: str | None) -> str | None:
    """Retrieve API key from AWS Secrets Manager."""
    if not secret_arn:
        return None
    try:
        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_arn)
        return response.get("SecretString", "")
    except Exception as e:
        logger.error(f"Failed to retrieve API key from Secrets Manager: {e}")
        return None
