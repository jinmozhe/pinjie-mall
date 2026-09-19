from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "production"]
RedisMode = Literal["disabled", "required"]
RequestLogMode = Literal["disabled", "metadata"]
UploadStorageDriver = Literal["local"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    project_name: str = Field(default="Pinjie Mall Backend", validation_alias="PROJECT_NAME")
    environment: Environment = Field(default="local", validation_alias="ENVIRONMENT")
    debug: bool = Field(default=False, validation_alias="DEBUG")
    api_v1_str: str = Field(default="/api/v1", validation_alias="API_V1_STR")
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    test_database_url: str | None = Field(default=None, validation_alias="TEST_DATABASE_URL")
    redis_mode: RedisMode = Field(default="required", validation_alias="REDIS_MODE")
    redis_url: str | None = Field(default=None, validation_alias="REDIS_URL")
    test_redis_url: str | None = Field(default=None, validation_alias="TEST_REDIS_URL")
    web_origins: list[str] = Field(
        default_factory=lambda: ["https://miniapp.invalid"],
        validation_alias="WEB_ORIGINS",
    )
    admin_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3001"],
        validation_alias="ADMIN_ORIGINS",
    )
    trusted_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"],
        validation_alias="TRUSTED_HOSTS",
    )
    trusted_proxy_cidrs: list[str] = Field(default_factory=list, validation_alias="TRUSTED_PROXY_CIDRS")
    force_https: bool = Field(default=False, validation_alias="FORCE_HTTPS")
    api_docs_enabled: bool | None = Field(default=None, validation_alias="API_DOCS_ENABLED")
    release_version: str | None = Field(default=None, validation_alias="RELEASE_VERSION")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_file_enabled: bool = Field(default=True, validation_alias="LOG_FILE_ENABLED")
    log_file_path: str | None = Field(
        default="logs/app_{time:YYYY-MM-DD}.log",
        validation_alias="LOG_FILE_PATH",
    )
    log_file_rotation: str = Field(default="50 MB", validation_alias="LOG_FILE_ROTATION")
    log_file_retention: str = Field(default="10 days", validation_alias="LOG_FILE_RETENTION")
    db_pool_size: int = Field(default=5, validation_alias="DB_POOL_SIZE", ge=1, le=50)
    db_max_overflow: int = Field(default=5, validation_alias="DB_MAX_OVERFLOW", ge=0, le=50)
    db_pool_timeout: float = Field(default=5.0, validation_alias="DB_POOL_TIMEOUT", gt=0, le=60)
    db_lock_timeout: float = Field(default=5.0, validation_alias="DB_LOCK_TIMEOUT", gt=0, le=60)
    dependency_timeout: float = Field(default=2.0, validation_alias="DEPENDENCY_TIMEOUT", gt=0, le=30)
    jwt_issuer: str = Field(default="pinjie-mall", validation_alias="JWT_ISSUER", min_length=3, max_length=128)
    web_jwt_secret: str | None = Field(default=None, validation_alias="WEB_JWT_SECRET")
    admin_jwt_secret: str | None = Field(default=None, validation_alias="ADMIN_JWT_SECRET")
    web_token_hmac_key: str | None = Field(default=None, validation_alias="WEB_TOKEN_HMAC_KEY")
    admin_token_hmac_key: str | None = Field(default=None, validation_alias="ADMIN_TOKEN_HMAC_KEY")
    auth_cookie_secure: bool = Field(default=False, validation_alias="AUTH_COOKIE_SECURE")
    web_access_ttl_seconds: int = Field(default=900, validation_alias="WEB_ACCESS_TTL_SECONDS", ge=300, le=1800)
    admin_access_ttl_seconds: int = Field(
        default=600,
        validation_alias="ADMIN_ACCESS_TTL_SECONDS",
        ge=300,
        le=900,
    )
    refresh_idle_ttl_days: int = Field(default=7, validation_alias="REFRESH_IDLE_TTL_DAYS", ge=1, le=14)
    session_absolute_ttl_days: int = Field(default=30, validation_alias="SESSION_ABSOLUTE_TTL_DAYS", ge=2, le=90)
    session_retention_days: int = Field(default=30, validation_alias="SESSION_RETENTION_DAYS", ge=1, le=365)
    password_hash_concurrency: int = Field(default=4, validation_alias="PASSWORD_HASH_CONCURRENCY", ge=1, le=16)
    request_log_mode: RequestLogMode = Field(default="disabled", validation_alias="REQUEST_LOG_MODE")
    security_event_retention_days: int = Field(
        default=180,
        validation_alias="SECURITY_EVENT_RETENTION_DAYS",
        ge=30,
        le=3650,
    )
    request_log_retention_days: int = Field(
        default=30,
        validation_alias="REQUEST_LOG_RETENTION_DAYS",
        ge=1,
        le=365,
    )
    request_log_stream_maxlen: int = Field(
        default=10000,
        validation_alias="REQUEST_LOG_STREAM_MAXLEN",
        ge=1000,
        le=1000000,
    )
    web_login_limit: int = Field(default=10, validation_alias="WEB_LOGIN_LIMIT", ge=1, le=100)
    admin_login_limit: int = Field(default=5, validation_alias="ADMIN_LOGIN_LIMIT", ge=1, le=20)
    login_window_seconds: int = Field(default=900, validation_alias="LOGIN_WINDOW_SECONDS", ge=60, le=3600)
    upload_storage_driver: UploadStorageDriver = Field(
        default="local",
        validation_alias="UPLOAD_STORAGE_DRIVER",
    )
    upload_local_root: Path = Field(default=Path("uploads"), validation_alias="UPLOAD_LOCAL_ROOT")
    upload_base_url: str = Field(default="/static/uploads", validation_alias="UPLOAD_BASE_URL")
    upload_max_file_size_mb: int = Field(
        default=50,
        validation_alias="UPLOAD_MAX_FILE_SIZE_MB",
        ge=1,
        le=100,
    )
    upload_allowed_extensions: str = Field(
        default="jpg,jpeg,png,webp,gif,pdf,doc,docx,xls,xlsx,zip",
        validation_alias="UPLOAD_ALLOWED_EXTENSIONS",
    )
    upload_io_concurrency: int = Field(
        default=4,
        validation_alias="UPLOAD_IO_CONCURRENCY",
        ge=1,
        le=16,
    )
    settings_media_root: Path = Field(default=Path("settings-media"), validation_alias="SETTINGS_MEDIA_ROOT")
    settings_media_base_url: str = Field(default="/static/settings", validation_alias="SETTINGS_MEDIA_BASE_URL")

    @field_validator("api_v1_str")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError("API_V1_STR must start with / and must not end with /")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be a supported standard logging level")
        return level

    @field_validator("upload_base_url", "settings_media_base_url")
    @classmethod
    def validate_upload_base_url(cls, value: str) -> str:
        if not value.startswith("/") or value == "/" or value.endswith("/"):
            raise ValueError("public media base URLs must be absolute paths without a trailing slash")
        if ".." in value.split("/"):
            raise ValueError("public media base URLs must not contain parent path segments")
        return value

    @field_validator("upload_local_root", "settings_media_root")
    @classmethod
    def validate_upload_local_root(cls, value: Path) -> Path:
        if not str(value).strip():
            raise ValueError("local media roots must not be empty")
        return value

    @field_validator("upload_allowed_extensions")
    @classmethod
    def validate_upload_allowed_extensions(cls, value: str) -> str:
        extensions = [item.strip().lower().removeprefix(".") for item in value.split(",")]
        if not extensions or any(not item or not item.isascii() or not item.isalnum() for item in extensions):
            raise ValueError("UPLOAD_ALLOWED_EXTENSIONS must be a comma-separated extension list")
        if "svg" in extensions:
            raise ValueError("UPLOAD_ALLOWED_EXTENSIONS must not include SVG")
        return ",".join(dict.fromkeys(extensions))

    @field_validator("web_origins", "admin_origins")
    @classmethod
    def normalize_browser_origins(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            origin = value[:-1] if value.endswith("/") else value
            parsed = urlsplit(origin)
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError("browser origins must use valid ports") from exc
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.hostname == "*":
                raise ValueError("browser origins must use explicit http(s) hosts")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("browser origins must not contain user information")
            if parsed.path or parsed.query or parsed.fragment:
                raise ValueError("browser origins must be absolute http(s) origins without paths")
            if port is None and parsed.netloc.endswith(":"):
                raise ValueError("browser origins must use valid ports")
            normalized.append(origin)
        return list(dict.fromkeys(normalized))

    def validate_runtime(self) -> None:
        self.validate_database_runtime()
        upload_root = self.upload_local_root.resolve()
        settings_root = self.settings_media_root.resolve()
        if (
            upload_root == settings_root
            or upload_root.is_relative_to(settings_root)
            or settings_root.is_relative_to(upload_root)
        ):
            raise ValueError("UPLOAD_LOCAL_ROOT and SETTINGS_MEDIA_ROOT must be separate sibling trees")
        upload_url = self.upload_base_url.rstrip("/") + "/"
        settings_url = self.settings_media_base_url.rstrip("/") + "/"
        if upload_url.startswith(settings_url) or settings_url.startswith(upload_url):
            raise ValueError("UPLOAD_BASE_URL and SETTINGS_MEDIA_BASE_URL must not overlap")
        if self.redis_mode != "required":
            raise ValueError("REDIS_MODE must be 'required' while authentication is enabled")
        if self.redis_url is None:
            raise ValueError("REDIS_URL is required when REDIS_MODE=required")
        if urlsplit(self.redis_url).scheme not in {"redis", "rediss"}:
            raise ValueError("REDIS_URL must use redis or rediss")
        if self.environment == "test":
            if self.test_redis_url is None:
                raise ValueError("TEST_REDIS_URL is required in test environment")
            if self.redis_url != self.test_redis_url:
                raise ValueError("REDIS_URL must match TEST_REDIS_URL in test environment")
        self._validate_authentication_secrets()
        self._validate_trusted_proxy_cidrs()
        self._validate_browser_origins()
        if self.session_absolute_ttl_days <= self.refresh_idle_ttl_days:
            raise ValueError("SESSION_ABSOLUTE_TTL_DAYS must be greater than REFRESH_IDLE_TTL_DAYS")
        if self.environment == "production":
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            if self.api_docs_enabled is True:
                raise ValueError("API_DOCS_ENABLED must remain false in production unless explicitly reviewed")
            if not self.release_version:
                raise ValueError("RELEASE_VERSION is required in production")
            if not self.trusted_hosts or "*" in self.trusted_hosts:
                raise ValueError("TRUSTED_HOSTS must be explicit in production")
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production")
            if not self.trusted_proxy_cidrs:
                raise ValueError("TRUSTED_PROXY_CIDRS must be explicit in production")

    def validate_database_runtime(self) -> None:
        if self.database_url is None:
            raise ValueError("DATABASE_URL is required")
        self._validate_database_url(self.database_url, "DATABASE_URL")
        if self.environment == "test":
            if self.test_database_url is None:
                raise ValueError("TEST_DATABASE_URL is required in test environment")
            self._validate_database_url(self.test_database_url, "TEST_DATABASE_URL")
            if self.database_url != self.test_database_url:
                raise ValueError("DATABASE_URL must match TEST_DATABASE_URL in test environment")
            database_name = urlsplit(self.test_database_url).path.removeprefix("/")
            if not database_name.endswith("_test"):
                raise ValueError("TEST_DATABASE_URL database name must end with _test")

    def _validate_authentication_secrets(self) -> None:
        named_values = {
            "WEB_JWT_SECRET": self.web_jwt_secret,
            "ADMIN_JWT_SECRET": self.admin_jwt_secret,
            "WEB_TOKEN_HMAC_KEY": self.web_token_hmac_key,
            "ADMIN_TOKEN_HMAC_KEY": self.admin_token_hmac_key,
        }
        values: list[str] = []
        for name, value in named_values.items():
            if value is None or len(value.encode("utf-8")) < 32:
                raise ValueError(f"{name} must contain at least 32 UTF-8 bytes")
            lowered = value.lower()
            if any(marker in lowered for marker in {"replace_with", "change_me", "example", "placeholder"}):
                raise ValueError(f"{name} must not use a template value")
            values.append(value)
        if len(set(values)) != len(values):
            raise ValueError("JWT and token HMAC keys must all be different")

    def _validate_trusted_proxy_cidrs(self) -> None:
        import ipaddress

        for value in self.trusted_proxy_cidrs:
            try:
                ipaddress.ip_network(value, strict=False)
            except ValueError as exc:
                raise ValueError(f"TRUSTED_PROXY_CIDRS contains an invalid network: {value}") from exc

    def _validate_browser_origins(self) -> None:
        if not self.web_origins:
            raise ValueError("WEB_ORIGINS must contain at least one explicit origin")
        if not self.admin_origins:
            raise ValueError("ADMIN_ORIGINS must contain at least one explicit origin")
        overlap = set(self.web_origins) & set(self.admin_origins)
        if overlap:
            raise ValueError("WEB_ORIGINS and ADMIN_ORIGINS must not overlap")

    @property
    def cors_origins(self) -> list[str]:
        return [*self.web_origins, *self.admin_origins]

    def authentication_secrets(self) -> tuple[str, str, str, str]:
        self._validate_authentication_secrets()
        # 使用显式检查而非 assert，确保在 python -O 优化模式下仍能正确验证
        if self.web_jwt_secret is None:
            raise RuntimeError("web_jwt_secret must not be None after validation")
        if self.admin_jwt_secret is None:
            raise RuntimeError("admin_jwt_secret must not be None after validation")
        if self.web_token_hmac_key is None:
            raise RuntimeError("web_token_hmac_key must not be None after validation")
        if self.admin_token_hmac_key is None:
            raise RuntimeError("admin_token_hmac_key must not be None after validation")
        return (
            self.web_jwt_secret,
            self.admin_jwt_secret,
            self.web_token_hmac_key,
            self.admin_token_hmac_key,
        )

    @property
    def allowed_upload_extensions(self) -> frozenset[str]:
        return frozenset(self.upload_allowed_extensions.split(","))

    @staticmethod
    def _validate_database_url(value: str, name: str) -> None:
        parsed = urlsplit(value)
        if parsed.scheme != "postgresql+asyncpg" or not parsed.hostname or not parsed.path:
            raise ValueError(f"{name} must be a postgresql+asyncpg URL")
        if parsed.path == "/" or parsed.path == "":
            raise ValueError(f"{name} must include a database name")

    @property
    def docs_url(self) -> str | None:
        enabled = self.api_docs_enabled
        if enabled is None:
            enabled = self.environment in {"local", "test"}
        return "/docs" if enabled else None

    @property
    def redoc_url(self) -> str | None:
        return "/redoc" if self.docs_url is not None else None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
