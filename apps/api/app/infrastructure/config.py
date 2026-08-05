from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Service Advisor for Independent Auto Repair Shops"
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://asa:asa@localhost:5432/ai_service_advisor"
    database_url_sync: str = "postgresql+psycopg://asa:asa@localhost:5432/ai_service_advisor"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-phase0-dev-secret-min-32-chars!!"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    api_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Phase 17 — production
    metrics_enabled: bool = True
    ready_require_redis: bool = False
    backup_dir: str = "/backups"

    # Modular AI — "heuristic" | "openai" (with local fallbacks) | "ollama"
    # openai mode fallbacks:
    #   AI: OpenAI → Ollama | STT: Whisper → Local Whisper | TTS: OpenAI → Piper
    ai_provider: str = "heuristic"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_stt_model: str = "whisper-1"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"
    openai_extraction_model: str = "gpt-4o-mini"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    # Local Whisper (OpenAI-compatible /v1/audio/transcriptions)
    local_whisper_url: str = "http://localhost:9000/v1"
    local_whisper_model: str = "whisper-1"
    # Piper TTS HTTP (POST / with {"text","voice"} → audio bytes)
    piper_url: str = "http://localhost:5000"
    piper_voice: str = "en_US-lessac-medium"

    audio_storage_dir: str = "storage/audio"
    max_audio_upload_mb: int = 25

    # Phase 5 — agent framework (see also AGENT_* env via AgentSettings)
    agents_enabled: bool = True

    # Phase 6 — Twilio SMS AI
    twilio_provider: str = "fake"  # fake | twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_status_callback_url: str = ""
    twilio_validate_signature: bool = True
    twilio_webhook_public_url: str = ""
    # Map shop Twilio numbers → shop UUID: "+15551111:uuid,+15552222:uuid"
    twilio_shop_map: str = ""
    sms_queue_backend: str = "memory"  # memory | redis
    sms_queue_max_attempts: int = 3
    sms_enabled: bool = True

    # Phase 7 — Twilio Voice AI
    voice_enabled: bool = True
    voice_provider: str = "fake"  # fake | twilio
    voice_queue_backend: str = "memory"  # memory | redis
    voice_queue_max_attempts: int = 3
    voice_tts_voice: str = "Polly.Joanna"
    voice_barge_in: bool = True
    voice_gather_timeout_sec: int = 5
    voice_gather_speech_timeout: str = "auto"
    voice_stream_enabled: bool = True
    # Map voice To-number → shop: "+15550001111:uuid" (falls back to twilio_shop_map)
    twilio_voice_shop_map: str = ""

    # SaaS foundation
    email_provider: str = "fake"  # fake | smtp
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@aiserviceadvisor.local"
    smtp_use_tls: bool = True
    otp_store_backend: str = "db"  # db | memory
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    billing_trial_days: int = 14
    billing_success_url: str = "http://localhost:3000/dashboard/billing?checkout=success"
    billing_cancel_url: str = "http://localhost:3000/dashboard/billing?checkout=cancel"
    web_app_url: str = "http://localhost:3000"
    # Comma-separated usernames allowed for /v1/admin/* and /v1/platform/*
    # (must match JWT username claim after normal login; empty deny-all in production)
    platform_admin_usernames: str = "ryanchen"
    # Dev bootstrap password for the first allowlisted admin (ignored in production)
    platform_admin_bootstrap_password: str = "Albert824@"
    # Legacy alias — ignored when platform_admin_usernames is set.
    platform_admin_emails: str = ""
    auth_rate_limit_per_minute: int = 30
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.05
    billing_portal_return_url: str = "http://localhost:3000/dashboard/billing"
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://localhost:3000/enterprise/sso/callback"

    # AI usage monitoring — estimated cost rates (microdollars = 1e-6 USD)
    usage_cost_input_per_1k_micros: int = 150  # ~$0.15 / 1M input tokens
    usage_cost_output_per_1k_micros: int = 600  # ~$0.60 / 1M output tokens
    usage_cost_stt_per_request_micros: int = 6000  # ~$0.006 / transcription
    usage_cost_tts_per_1k_chars_micros: int = 15000  # ~$15 / 1M chars
    usage_cost_sms_micros: int = 7900  # ~$0.0079 / SMS
    usage_cost_voice_per_minute_micros: int = 13000  # ~$0.013 / voice minute

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]
        # Local web often runs on either localhost or 127.0.0.1; browsers treat them
        # as different origins, so mirror both in non-production.
        if self.environment.lower() not in {"production", "prod"}:
            mirrored: list[str] = []
            for origin in origins:
                mirrored.append(origin)
                if "://localhost" in origin:
                    mirrored.append(origin.replace("://localhost", "://127.0.0.1", 1))
                elif "://127.0.0.1" in origin:
                    mirrored.append(origin.replace("://127.0.0.1", "://localhost", 1))
            # Preserve order, drop duplicates
            seen: set[str] = set()
            origins = []
            for origin in mirrored:
                if origin not in seen:
                    seen.add(origin)
                    origins.append(origin)
        return origins

    @property
    def platform_admin_username_set(self) -> set[str]:
        return {u.strip().lower() for u in self.platform_admin_usernames.split(",") if u.strip()}

    @property
    def platform_admin_email_set(self) -> set[str]:
        """Deprecated — prefer platform_admin_username_set."""
        return {e.strip().lower() for e in self.platform_admin_emails.split(",") if e.strip()}


settings = Settings()
