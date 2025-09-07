import json
import os
import uuid
from io import BytesIO

from minio import Minio
from minio.error import S3Error

from src.utils import logger


class _MinioClient:
    """
    A private client for interacting with a MinIO server.
    It reads connection details from environment variables and provides
    methods for uploading files and ensuring buckets exist.
    """

    def __init__(self):
        """
        Initializes the Minio client.
        Reads configuration from environment variables set in docker-compose.yml.
        """
        minio_uri = os.getenv("MINIO_URI", "http://milvus-minio:9000")
        self.endpoint = minio_uri.split("://")[-1]
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")

        if os.getenv("RUNNING_IN_DOCKER"):
            host_ip = os.getenv("HOST_IP", "localhost")
            self.public_endpoint = f"{host_ip}:{self.endpoint.split(':')[-1]}"
        else:
            self.public_endpoint = self.endpoint

        try:
            self.client = Minio(self.endpoint, access_key=self.access_key, secret_key=self.secret_key, secure=False)
        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {e}")
            raise

    def ensure_bucket_exists(self, bucket_name: str):
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info(f"Bucket '{bucket_name}' created.")
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"AWS": ["*"]},
                            "Action": ["s3:GetObject"],
                            "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                        },
                    ],
                }
                self.client.set_bucket_policy(bucket_name, json.dumps(policy))
                logger.info(f"Public read policy set for bucket '{bucket_name}'.")
        except S3Error as e:
            logger.error(f"Error with bucket '{bucket_name}': {e}")
            raise

    def upload_file(self, bucket_name: str, file_name: str, data: bytes, content_type: str) -> str:
        self.ensure_bucket_exists(bucket_name)
        try:
            data_stream = BytesIO(data)
            self.client.put_object(bucket_name, file_name, data_stream, length=len(data), content_type=content_type)
            logger.info(f"Successfully uploaded '{file_name}' to bucket '{bucket_name}'.")
            return f"http://{self.public_endpoint}/{bucket_name}/{file_name}"
        except S3Error as e:
            logger.error(f"Failed to upload file '{file_name}' to MinIO: {e}")
            raise


# Singleton instance of the private client
_minio_client = _MinioClient()


def upload_image_to_minio(data: bytes, file_extension: str = "jpg") -> str:
    """
    Uploads image data to a predefined MinIO bucket and returns the public URL.

    This function abstracts away the details of MinIO client management,
    bucket creation, and file naming.

    Args:
        data (bytes): The raw image data.
        file_extension (str): The file extension for the image (e.g., "jpg", "png").

    Returns:
        str: The public URL of the uploaded image.

    Raises:
        ConnectionError: If the upload to the file server fails.
    """
    try:
        bucket_name = "generated-images"
        file_name = f"{uuid.uuid4()}.{file_extension}"
        content_type = f"image/{file_extension}"

        image_url = _minio_client.upload_file(
            bucket_name=bucket_name, file_name=file_name, data=data, content_type=content_type
        )
        return image_url
    except Exception as e:
        logger.error(f"High-level upload to MinIO failed: {e}")
        raise ConnectionError(f"Failed to upload image to file server: {e}")
