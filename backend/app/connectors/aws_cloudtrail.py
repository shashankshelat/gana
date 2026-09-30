import json
import logging
from typing import Optional

from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector

logger = logging.getLogger(__name__)


@register_connector
class AWSCloudTrailConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="aws_cloudtrail",
        display_name="AWS CloudTrail",
        description="Ingest AWS API and management events from CloudTrail via S3 or CloudWatch Logs",
        icon="cloud",
        category="cloud",
        auth_methods=["api_key"],
        supports_polling=True,
        default_ocsf_class_uid=3005,
        config_schema={
            "properties": {
                "aws_access_key_id": {"type": "string", "title": "AWS Access Key ID", "secret": True},
                "aws_secret_access_key": {"type": "string", "title": "AWS Secret Access Key", "secret": True},
                "aws_region": {"type": "string", "title": "AWS Region", "default": "us-east-1"},
                "source_type": {"type": "string", "title": "Source", "enum": ["s3", "cloudwatch"], "default": "cloudwatch"},
                "s3_bucket": {"type": "string", "title": "S3 Bucket Name"},
                "s3_prefix": {"type": "string", "title": "S3 Key Prefix", "default": "AWSLogs/"},
                "cloudwatch_log_group": {"type": "string", "title": "CloudWatch Log Group"},
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 300},
            },
            "required": ["aws_access_key_id", "aws_secret_access_key", "aws_region"],
        },
        default_mapping={
            "time": "eventTime",
            "cloud.account.uid": "recipientAccountId",
            "cloud.region": "awsRegion",
            "actor.user.uid": "userIdentity.arn",
            "actor.user.name": "userIdentity.userName",
            "actor.user.type": "userIdentity.type",
            "api.operation": "eventName",
            "api.service.name": "eventSource",
            "src_endpoint.ip": "sourceIPAddress",
            "http_request.user_agent": "userAgent",
            "status_id": {"path": "errorCode", "transform": "str"},
        },
    )

    async def validate_config(self) -> tuple[bool, str]:
        required = ["aws_access_key_id", "aws_secret_access_key", "aws_region"]
        for field in required:
            if not self.config.get(field):
                return False, f"{field} is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            import boto3
            client = boto3.client(
                "sts",
                aws_access_key_id=self.config["aws_access_key_id"],
                aws_secret_access_key=self.config["aws_secret_access_key"],
                region_name=self.config["aws_region"],
            )
            identity = client.get_caller_identity()
            return True, f"Connected as {identity['Arn']}"
        except Exception as e:
            return False, str(e)

    async def fetch_events(self, since: Optional[str] = None) -> list[dict]:
        source_type = self.config.get("source_type", "cloudwatch")
        if source_type == "s3":
            return await self._fetch_from_s3(since)
        return await self._fetch_from_cloudwatch(since)

    async def _fetch_from_cloudwatch(self, since: Optional[str] = None) -> list[dict]:
        import boto3
        import time

        client = boto3.client(
            "logs",
            aws_access_key_id=self.config["aws_access_key_id"],
            aws_secret_access_key=self.config["aws_secret_access_key"],
            region_name=self.config["aws_region"],
        )
        log_group = self.config.get("cloudwatch_log_group")
        if not log_group:
            return []

        end_time = int(time.time() * 1000)
        start_time = end_time - 3600000  # last hour by default

        events = []
        try:
            paginator = client.get_paginator("filter_log_events")
            for page in paginator.paginate(
                logGroupName=log_group,
                startTime=start_time,
                endTime=end_time,
                limit=10000,
            ):
                for event in page.get("events", []):
                    try:
                        parsed = json.loads(event["message"])
                        events.append(parsed)
                    except json.JSONDecodeError:
                        events.append({"message": event["message"], "timestamp": event["timestamp"]})
        except Exception as e:
            logger.error("CloudWatch fetch error: %s", e)
        return events

    async def _fetch_from_s3(self, since: Optional[str] = None) -> list[dict]:
        import boto3
        import gzip

        s3 = boto3.client(
            "s3",
            aws_access_key_id=self.config["aws_access_key_id"],
            aws_secret_access_key=self.config["aws_secret_access_key"],
            region_name=self.config["aws_region"],
        )
        bucket = self.config.get("s3_bucket")
        prefix = self.config.get("s3_prefix", "AWSLogs/")
        if not bucket:
            return []

        events = []
        try:
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix, MaxKeys=100):
                for obj in page.get("Contents", []):
                    if not obj["Key"].endswith(".json.gz"):
                        continue
                    resp = s3.get_object(Bucket=bucket, Key=obj["Key"])
                    content = gzip.decompress(resp["Body"].read())
                    data = json.loads(content)
                    events.extend(data.get("Records", []))
                    if len(events) >= 10000:
                        break
        except Exception as e:
            logger.error("S3 fetch error: %s", e)
        return events
