"""humilis-dynamodb: serve S3 files in a DynamoDB-backed REST API"""


from collections import defaultdict
from gzip import GzipFile
from io import BytesIO, StringIO
import json
import time

import boto3
import botocore

from humilis_dynamodb import config


class WriteError(Exception):
    pass


def get_client(role_arn=None):
    """Get S3 client."""

    if role_arn is None:
        return boto3.client("s3")
    else:
        credentials = boto3.client("sts").assume_role(
            RoleArn=role_arn, RoleSessionName="abc")["Credentials"]
        return boto3.client(
            "s3",
            aws_access_key_id = credentials['AccessKeyId'],
            aws_secret_access_key = credentials['SecretAccessKey'],
            aws_session_token = credentials['SessionToken'])


def get_resource(role_arn=None):
    """Get S3 resource."""

    if role_arn is None:
        return boto3.resource("s3")
    else:
        credentials = boto3.client("sts").assume_role(
            RoleArn=role_arn, RoleSessionName="abc")["Credentials"]
        return boto3.resource(
            "s3",
            aws_access_key_id = credentials['AccessKeyId'],
            aws_secret_access_key = credentials['SecretAccessKey'],
            aws_session_token = credentials['SessionToken'])


def load_s3_object(key, bucket, decompress=True, role_arn=None):
    """Load an object from S3. Returns a file object."""

    s3 = get_client(role_arn=role_arn)
    obj = s3.get_object(Bucket=bucket, Key=key)

    if decompress:
        f = GzipFile(None, "rb", fileobj=BytesIO(obj['Body'].read()))
    else:
        f = obj['Body']

    return StringIO(f.read().decode("utf-8"))


def save_s3_object(data, key, bucket, format="json", role_arn=None):
    """Save dict object to S3 in DynamoDB import format."""

    s3_resource = get_resource(role_arn=role_arn)
    format = format.lower()
    key = key.format(format=format)
    o = BytesIO()
    with GzipFile(fileobj=o, mode="wb") as f:
        for k, v in sorted(data.items()):
            if format == "dynamodb":
                obj = {"key": {"S": k}, "value": {"S": json.dumps(v)}}
            elif format == "json":
                obj = {k: v}
            f.write((json.dumps(obj) + "\n").encode())

    s3_resource.Bucket(bucket).put_object(Body=o.getvalue(), Key=key)
    return "s3://{}/{}".format(bucket, key)


def s3_to_dynamodb(key, tablename, bucket, ignore_row=None):
    """Push S3 object to DynamoDB."""
    dynamodb = Table(tablename)
    dynamodb.scale_up()
    for row in load_s3_object(key, bucket):
        if ignore_row is not None and ignore_row(row):
            continue
        dynamodb.write_item(row)
    dynamodb.flush()
    dynamodb.scale_down()


def capacity_setter(func):
    """Do not throw an error when we are not changing the current capacity."""

    def wrapper(self):
        try:
            val = func(self)
            time.sleep(config.WAIT_TO_SCALE)  # Wait for DynamoDB to scale
            return val
        except botocore.exceptions.ClientError as err:
            if "throughput for the table will not change" in str(err):
                pass
            else:
                raise

    return wrapper


class Table:

    """Facade to a DynamoDB table."""

    def __init__(
            self,
            name,
            wait=config.INITIAL_WAIT):
        self._name = name
        self._client = boto3.client("dynamodb")
        self._resource = boto3.resource("dynamodb").Table(self._name)
        self._wait = wait
        self._batch = []
        self._rcount = 0
        self._tcount = 0
        self._t0 = None

    @property
    def capacity(self):
        """The current read/write capacity of the table."""
        return {k: v for k, v in self._resource.provisioned_throughput.items()
                if k in {"ReadCapacityUnits", "WriteCapacityUnits"}}

    @capacity_setter
    def scale_up(self):
        """Prepare the table for a push by increasing the write capacity."""
        self._resource.update(
            ProvisionedThroughput={
                "WriteCapacityUnits": config.PUSH_WRITE_CAPACITY,
                "ReadCapacityUnits": self.capacity["ReadCapacityUnits"]})

    @capacity_setter
    def scale_down(self):
        """Put the capacity back to its baseline values."""
        self._resource.update(
            ProvisionedThroughput={
                'WriteCapacityUnits': config.BASELINE_WRITE_CAPACITY,
                'ReadCapacityUnits': self.capacity["ReadCapacityUnits"]})

    def flush(self):
        """Flush the items that haven't been pushed to DynamoDB yet."""
        while self._batch:
            self._batch_write_item()

    def write_item(self, item):
        """Writes a single item, using BatchWriteItem under the hood."""
        if self._t0 is None:
            self._t0 = time.time()
        if len(self._batch) < 25:
            self._batch.append({"PutRequest": {"Item": json.loads(item)}})
        if len(self._batch) == 25:
            self._batch_write_item()
            self._rcount += (25 - len(self._batch))
            self._tcount += (25 - len(self._batch))
            if self._rcount >= config.REPORT_EVERY:
                print("{0:<8} ... {1} WPS".format(
                    self._tcount,
                    round(self._tcount/(time.time()-self._t0)),
                    flush=True))
                self._rcount = 0

    def _batch_write_item(self):
        """A wrapper around DynamoDB's batch_write_item."""
        try:
            time.sleep(self._wait)
            r = self._client.batch_write_item(RequestItems={self._name: self._batch})
        except botocore.exceptions.ParamValidationError:
            # This is not retryable
            raise
        except Exception:
            # lazy to handle all exceptions properly: Fix it!
            # For now we just assume the error is retryable and we keep 
            # trying, but we wait more every time we try.
            self._wait *= config.WAIT_MORE_FACTOR
            if self._wait > config.MAX_WAIT:
                raise
            return
        unprocessed = r["UnprocessedItems"].get(self._name, [])
        if unprocessed:
            self._wait *= config.WAIT_MORE_FACTOR
            if self._wait > config.MAX_WAIT:
                raise WriteError("Unable to push items to DynamoDB.")
        else:
            self._wait *= config.WAIT_LESS_FACTOR
        self._batch = unprocessed
