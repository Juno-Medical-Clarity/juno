from google.cloud import storage
import uuid
from datetime import datetime, timedelta

class StorageService:
    """Service for uploading files to Google Cloud Storage"""
    
    def __init__(self, bucket_name: str, project_id: str = None):
        self.client = storage.Client(project=project_id)
        self.bucket = self.client.bucket(bucket_name)
    
    def upload_audio_file(self, audio_content: bytes, filename: str, content_type: str = 'audio/wav') -> str:
        """
        Upload audio file to Google Cloud Storage
        
        Args:
            audio_content: Audio file content in bytes
            filename: Filename/path in GCS (can include appointment_id for organization)
            content_type: MIME type of the audio file
            
        Returns:
            GCS URI in format gs://bucket-name/path/to/file
        """
        
        # Create blob and upload
        blob = self.bucket.blob(filename)
        blob.upload_from_string(audio_content, content_type=content_type)
        
        # Return the GCS URI (required for Speech-to-Text API)
        return f"gs://{self.bucket.name}/{filename}"
    
    def get_signed_url(self, blob_name: str, expiration_minutes: int = 60) -> str:
        """
        Generate a signed URL for secure access to a file
        
        Args:
            blob_name: Name of the blob in storage
            expiration_minutes: URL expiration time in minutes
            
        Returns:
            Signed URL
        """
        from datetime import timedelta
        
        blob = self.bucket.blob(blob_name)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET"
        )
        
        return url
    
    def upload_file(self, file_content: bytes, filename: str, content_type: str) -> str:
        """
        Upload any file to Google Cloud Storage
        
        Args:
            file_content: File content in bytes
            filename: Filename/path in GCS
            content_type: MIME type of the file (e.g., 'application/pdf', 'audio/webm')
            
        Returns:
            GCS URI in format gs://bucket-name/path/to/file
        """
        blob = self.bucket.blob(filename)
        blob.upload_from_string(file_content, content_type=content_type)
        return f"gs://{self.bucket.name}/{filename}"
    
    def download_file(self, gcs_uri: str) -> bytes:
        """
        Download a file from Google Cloud Storage by its GCS URI
        
        Args:
            gcs_uri: GCS URI in format gs://bucket-name/path/to/file
            
        Returns:
            File content as bytes
        """
        # Parse the GCS URI to extract the blob path
        # Format: gs://bucket-name/path/to/file
        if gcs_uri.startswith("gs://"):
            path = gcs_uri.split(f"gs://{self.bucket.name}/", 1)
            if len(path) == 2:
                blob_name = path[1]
            else:
                raise ValueError(f"GCS URI does not match bucket: {gcs_uri}")
        else:
            blob_name = gcs_uri
        
        blob = self.bucket.blob(blob_name)
        return blob.download_as_bytes()

    def delete_folder(self, folder_prefix: str) -> int:
        """
        Delete all files in a folder (prefix)
        
        Args:
            folder_prefix: Folder path prefix (e.g., 'recordings/appointment-id/')
            
        Returns:
            Number of files deleted
        """
        blobs = self.bucket.list_blobs(prefix=folder_prefix)
        deleted_count = 0
        
        for blob in blobs:
            blob.delete()
            deleted_count += 1
            print(f"[Storage] Deleted: {blob.name}")
        
        return deleted_count
