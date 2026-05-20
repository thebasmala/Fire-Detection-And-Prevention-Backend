"""Frame image storage: Cloudinary when configured, else local uploads + static URLs."""

from __future__ import annotations

import logging
import uuid
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

ALLOWED_FRAME_EXT = {".jpg", ".jpeg", ".png", ".webp"}
FOLDER_FIRE_FRAMES = "fire_frames"
FOLDER_DEVICE_FRAMES = "device_frames"


def _cloudinary_available() -> bool:
    try:
        import cloudinary  # noqa: F401
        return True
    except ImportError:
        return False


def cloudinary_configured() -> bool:
    return bool(
        (settings.cloudinary_cloud_name or "").strip()
        and (settings.cloudinary_api_key or "").strip()
        and (settings.cloudinary_api_secret or "").strip()
        and _cloudinary_available()
    )


def _normalize_suffix(filename: str) -> str:
    suffix = Path(filename or "frame.jpg").suffix.lower()
    return suffix if suffix in ALLOWED_FRAME_EXT else ".jpg"


def _local_paths(folder: str) -> Tuple[Path, str]:
    """Return (upload_dir, url_path_segment) for local fallback."""
    if folder == FOLDER_FIRE_FRAMES:
        return Path(settings.fire_frames_upload_dir), "fire_frames"
    if folder == FOLDER_DEVICE_FRAMES:
        return Path(settings.frames_upload_dir), "frames"
    raise ValueError(f"Unknown storage folder: {folder}")


def _save_local(
    data: bytes,
    folder: str,
    *,
    original_filename: str,
    public_base_url: str,
) -> Tuple[str, str]:
    upload_dir, url_segment = _local_paths(folder)
    suffix = _normalize_suffix(original_filename)
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    dest = upload_dir / safe_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    base = public_base_url.rstrip("/")
    public_url = f"{base}/static/{url_segment}/{safe_name}"
    logger.info("Frame saved locally: %s", public_url)
    return public_url, safe_name


def _save_cloudinary(data: bytes, folder: str, *, original_filename: str) -> Tuple[str, str]:
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name.strip(),
        api_key=settings.cloudinary_api_key.strip(),
        api_secret=settings.cloudinary_api_secret.strip(),
        secure=True,
    )
    suffix = _normalize_suffix(original_filename)
    public_id = uuid.uuid4().hex
    result = cloudinary.uploader.upload(
        BytesIO(data),
        folder=folder,
        public_id=public_id,
        resource_type="image",
        format=suffix.lstrip("."),
    )
    public_url = str(result.get("secure_url") or result.get("url", "")).strip()
    stored_name = str(result.get("public_id") or public_id)
    if not public_url:
        raise RuntimeError("Cloudinary upload returned no URL")
    logger.info("Frame saved to Cloudinary (%s): %s", folder, public_url)
    return public_url, stored_name


def save_image_bytes(
    data: bytes,
    folder: str,
    *,
    original_filename: str = "frame.jpg",
    public_base_url: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Persist frame bytes and return (public_url, stored_filename_or_public_id).

    folder: ``fire_frames`` or ``device_frames`` (Cloudinary folder name).
    """
    if not data:
        raise ValueError("Empty file")

    if folder not in (FOLDER_FIRE_FRAMES, FOLDER_DEVICE_FRAMES):
        raise ValueError(f"folder must be {FOLDER_FIRE_FRAMES!r} or {FOLDER_DEVICE_FRAMES!r}")

    if cloudinary_configured():
        return _save_cloudinary(data, folder, original_filename=original_filename)

    if (
        (settings.cloudinary_cloud_name or "").strip()
        and (settings.cloudinary_api_key or "").strip()
        and (settings.cloudinary_api_secret or "").strip()
        and not _cloudinary_available()
    ):
        logger.warning(
            "CLOUDINARY_* set but cloudinary package not installed; using local storage. "
            "Run: pip install -r requirements.txt"
        )

    if not public_base_url:
        raise ValueError("public_base_url required for local frame storage")
    return _save_local(
        data,
        folder,
        original_filename=original_filename,
        public_base_url=public_base_url,
    )
