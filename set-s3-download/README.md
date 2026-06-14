# Set S3 Download

Bash script that updates S3 object metadata so files are downloaded as attachments instead of opened in the browser.

## What it does

For each object under the given bucket prefix, sets:

- `Content-Type: application/octet-stream`
- `Content-Disposition: attachment; filename="<original-filename>"`

## Requirements

- [AWS CLI](https://aws.amazon.com/cli/) configured with credentials for the target bucket

## Usage

```bash
chmod +x set-s3-download.sh

./set-s3-download.sh <bucket> <prefix> [region]
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `bucket` | yes | S3 bucket name |
| `prefix` | yes | Object prefix, e.g. `videos/2026/` |
| `region` | no | AWS region. Defaults to `AWS_DEFAULT_REGION`, then `aws configure get region`, then `us-east-1` |

### Example

```bash
./set-s3-download.sh my-bucket training/videos/2026/ us-east-1
```

## Related

Used automatically by [`upload-videos-to-s3`](../upload-videos-to-s3/README.md) after file upload.
