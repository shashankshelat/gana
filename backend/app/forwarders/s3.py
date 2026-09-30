import json
import gzip
import time
import uuid
from app.forwarders.base import BaseForwarder, ForwarderMeta, review_fields
from app.forwarders.registry import register_forwarder


@register_forwarder
class S3Forwarder(BaseForwarder):
    meta = ForwarderMeta(
        type_id="s3",
        display_name="AWS S3",
        description="Forward OCSF events to AWS S3 as compressed NDJSON files (Parquet-ready)",
        icon="aws",
        category="storage",
        max_batch_size=50000,
        config_schema={
            "properties": {
                "bucket": {"type": "string", "title": "S3 Bucket Name"},
                "prefix": {"type": "string", "title": "Key Prefix", "default": "ocsf/events/"},
                **review_fields("review_prefix", "Review key prefix for unclassified events (blank = same)", "ocsf/review/"),
                "aws_region": {"type": "string", "title": "AWS Region", "default": "us-east-1"},
                "aws_access_key_id": {"type": "string", "title": "AWS Access Key ID", "secret": True},
                "aws_secret_access_key": {"type": "string", "title": "AWS Secret Access Key", "secret": True},
                "aws_role_arn": {"type": "string", "title": "IAM Role ARN (for cross-account)"},
                "partition_by": {
                    "type": "string",
                    "title": "Partition By",
                    "enum": ["date", "class_name", "none"],
                    "default": "date",
                },
                "compression": {
                    "type": "string",
                    "title": "Compression",
                    "enum": ["gzip", "none"],
                    "default": "gzip",
                },
                "format": {
                    "type": "string",
                    "title": "File Format",
                    "enum": ["ndjson", "json"],
                    "default": "ndjson",
                },
            },
            "required": ["bucket"],
        },
    )

    def _get_s3_client(self):
        import boto3
        kwargs = {"region_name": self.config.get("aws_region", "us-east-1")}
        if self.config.get("aws_access_key_id"):
            kwargs["aws_access_key_id"] = self.config["aws_access_key_id"]
            kwargs["aws_secret_access_key"] = self.config.get("aws_secret_access_key", "")
        return boto3.client("s3", **kwargs)

    async def validate_config(self) -> tuple[bool, str]:
        if not self.config.get("bucket"):
            return False, "bucket is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            s3 = self._get_s3_client()
            s3.head_bucket(Bucket=self.config["bucket"])
            return True, f"Bucket {self.config['bucket']} is accessible"
        except Exception as e:
            return False, str(e)

    def _build_key(self, events: list[dict], prefix: str | None = None) -> str:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        prefix = (prefix or self.config.get("prefix", "ocsf/events/")).rstrip("/")
        partition_by = self.config.get("partition_by", "date")

        if partition_by == "date":
            partition = f"year={now.year}/month={now.month:02d}/day={now.day:02d}/hour={now.hour:02d}"
        elif partition_by == "class_name":
            class_name = events[0].get("class_name", "unknown").replace(" ", "_").lower() if events else "unknown"
            partition = f"class_name={class_name}/year={now.year}/month={now.month:02d}/day={now.day:02d}"
        else:
            partition = ""

        file_id = str(uuid.uuid4())[:8]
        ext = ".ndjson.gz" if self.config.get("compression", "gzip") == "gzip" else ".ndjson"
        parts = [prefix, partition, f"ocsf_{int(now.timestamp())}_{file_id}{ext}"]
        return "/".join(p for p in parts if p)

    async def forward(self, events: list[dict]) -> tuple[int, int]:
        review_prefix = self.config.get("review_prefix")
        if review_prefix and any(self.is_review(e) for e in events):
            # Unclassified events go to their own objects under the review prefix
            main = [e for e in events if not self.is_review(e)]
            review = [e for e in events if self.is_review(e)]
            s1, f1 = await self._write(main, None)
            s2, f2 = await self._write(review, review_prefix)
            return s1 + s2, f1 + f2
        return await self._write(events, None)

    async def _write(self, events: list[dict], prefix: str | None) -> tuple[int, int]:
        if not events:
            return 0, 0
        try:
            s3 = self._get_s3_client()
            fmt = self.config.get("format", "ndjson")
            compression = self.config.get("compression", "gzip")

            clean_events = [{k: v for k, v in e.items() if not k.startswith("_")} for e in events]

            if fmt == "ndjson":
                content = "\n".join(json.dumps(e) for e in clean_events)
            else:
                content = json.dumps(clean_events, indent=2)

            data = content.encode("utf-8")
            if compression == "gzip":
                data = gzip.compress(data)

            key = self._build_key(events, prefix)
            content_type = "application/x-ndjson" if fmt == "ndjson" else "application/json"
            if compression == "gzip":
                content_type = "application/gzip"

            s3.put_object(
                Bucket=self.config["bucket"],
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata={
                    "ocsf-event-count": str(len(events)),
                    "ocsf-source": "gana",
                },
            )
            return len(events), 0
        except Exception as e:
            return 0, len(events)
