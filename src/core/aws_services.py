# src/core/aws_services.py
"""AWS SDK wrappers for S3 and Secrets Manager integration."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

LOGGER = logging.getLogger(__name__)


class S3StateManager:
    """Manages state file persistence in S3."""

    def __init__(self, bucket_name: str, region: Optional[str] = None) -> None:
        """Initialize S3 client for state management.

        Args:
            bucket_name: Name of the S3 bucket for state storage.
            region: AWS region. If None, uses default region from AWS config.

        """
        self.bucket_name = bucket_name
        self.s3_client = boto3.client("s3", region_name=region)
        self.state_key = "state/last_video_id.json"

    def load_state(self) -> Dict[str, Any]:
        """Load state from S3 bucket.

        Returns:
            Deserialized JSON payload. Returns an empty dictionary when missing or invalid.

        Raises:
            ClientError: If S3 operation fails (other than missing object).

        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=self.state_key)
            content = response["Body"].read().decode("utf-8")
            data = json.loads(content)
            LOGGER.debug("Loaded state from S3: %s/%s", self.bucket_name, self.state_key)
            return data if isinstance(data, dict) else {}
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "NoSuchKey":
                LOGGER.info("State file not found in S3, returning empty state")
                return {}
            LOGGER.error("Failed to load state from S3: %s", exc)
            raise
        except json.JSONDecodeError as exc:
            LOGGER.warning("Invalid JSON in state file, returning empty state: %s", exc)
            return {}

    def save_state(self, data: Dict[str, Any]) -> None:
        """Save state to S3 bucket.

        Args:
            data: Dictionary to serialize and save as JSON.

        Raises:
            ClientError: If S3 operation fails.

        """
        try:
            content = json.dumps(data, indent=2)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=self.state_key,
                Body=content.encode("utf-8"),
                ContentType="application/json",
            )
            LOGGER.debug("Saved state to S3: %s/%s", self.bucket_name, self.state_key)
        except ClientError as exc:
            LOGGER.error("Failed to save state to S3: %s", exc)
            raise


class SecretsManagerClient:
    """Client for retrieving secrets from AWS Secrets Manager."""

    def __init__(self, region: Optional[str] = None) -> None:
        """Initialize Secrets Manager client.

        Args:
            region: AWS region. If None, uses default region from AWS config.

        """
        self.secrets_client = boto3.client("secretsmanager", region_name=region)

    def get_secret(self, secret_name: str) -> Dict[str, Any]:
        """Retrieve and parse JSON secret from Secrets Manager.

        Args:
            secret_name: Name or ARN of the secret in Secrets Manager.

        Returns:
            Parsed JSON secret as a dictionary.

        Raises:
            ClientError: If Secrets Manager operation fails.
            ValueError: If secret value is not valid JSON.

        """
        try:
            response = self.secrets_client.get_secret_value(SecretId=secret_name)
            secret_string = response.get("SecretString", "")

            if not secret_string:
                raise ValueError(f"Secret {secret_name} has empty SecretString")

            secret_data = json.loads(secret_string)
            if not isinstance(secret_data, dict):
                raise ValueError(f"Secret {secret_name} is not a JSON object")

            LOGGER.debug("Successfully retrieved secret: %s", secret_name)
            return secret_data
        except json.JSONDecodeError as exc:
            LOGGER.error("Secret %s contains invalid JSON: %s", secret_name, exc)
            raise ValueError(f"Secret {secret_name} is not valid JSON") from exc
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                LOGGER.error("Secret %s not found in Secrets Manager", secret_name)
            elif error_code == "AccessDeniedException":
                LOGGER.error("Access denied to secret %s. Check IAM permissions", secret_name)
            else:
                LOGGER.error("Failed to retrieve secret %s: %s", secret_name, exc)
            raise

