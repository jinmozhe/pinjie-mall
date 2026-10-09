from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class CacheKeys:
    project: str
    environment: str

    def _key(self, domain: str, purpose: str, identifier: str, *, version: int = 1) -> str:
        return f"{self.project}:{self.environment}:{domain}:{purpose}:v{version}:{identifier}"

    def web_session(self, session_id: str) -> str:
        return self._key("auth-web", "session", session_id)

    def admin_session(self, session_id: str) -> str:
        return self._key("auth-admin", "session", session_id)

    def miniapp(self, purpose: str, digest: str) -> str:
        return self._key("auth-miniapp", purpose, digest)

    def refresh_lock(self, digest: str, *, admin: bool = False) -> str:
        domain = "auth-admin" if admin else "auth-web"
        return self._key(domain, "refresh-lock", digest)

    def login_ip(self, digest: str, *, admin: bool = False) -> str:
        domain = "auth-admin" if admin else "auth-web"
        return self._key(domain, "login-ip", digest)

    def login_identifier(self, digest: str, *, admin: bool = False) -> str:
        domain = "auth-admin" if admin else "auth-web"
        return self._key(domain, "login-id", digest)

    def request_log_stream(self) -> str:
        return self._key("system", "request-log", "events")

    def request_log_dead_letter(self) -> str:
        return self._key("system", "request-log-dlq", "events")

    def system_telemetry(self) -> str:
        return self._key("system", "telemetry", "overview")


def cache_keys(settings: Settings) -> CacheKeys:
    project = settings.project_name.lower().replace(" ", "-")
    return CacheKeys(project=project, environment=settings.environment)


__all__ = ["CacheKeys", "cache_keys"]
