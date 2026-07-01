import logging
import re

class SecretMasker(logging.Filter):
    """Logging filter that redacts sensitive API keys and Bearer tokens from log outputs."""
    
    MASK_PATTERNS = [
        (re.compile(r"nvapi-[a-zA-Z0-9_-]+", re.IGNORECASE), "nvapi-***REDACTED***"),
        (re.compile(r"Bearer\s+[a-zA-Z0-9\._-]+", re.IGNORECASE), "Bearer ***REDACTED***"),
        (re.compile(r"api_key\s*=\s*['\"]?[a-zA-Z0-9_-]+['\"]?", re.IGNORECASE), "api_key=***REDACTED***"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.mask_text(record.msg)
        if record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    new_args.append(self.mask_text(arg))
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)
        return True

    @classmethod
    def mask_text(cls, text: str) -> str:
        for pattern, replacement in cls.MASK_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

def install_secret_masker():
    """Installs the SecretMasker filter globally on the root logger."""
    masker = SecretMasker()
    logging.getLogger().addFilter(masker)
