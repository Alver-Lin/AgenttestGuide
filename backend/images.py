"""Supported local Markdown image attachments (no remote upload service)."""

MAX_IMAGE_BYTES = 10 * 1024 * 1024


def image_extension(data: bytes):
    # Detect the content rather than trusting the uploaded name or MIME header.
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return '.gif'
    if len(data) >= 16 and data[:4] == b'RIFF' and data[8:12] == b'WEBP' and data[12:16] in (b'VP8 ', b'VP8L', b'VP8X'):
        return '.webp'
    return None
