"""
ICU智能预警系统 - 配置加载
从 .env 读取敏感信息，从 config.yaml 读取业务配置
"""
import os
import yaml
from urllib.parse import quote_plus
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """环境变量配置（敏感信息）"""

    # SmartCare
    SMARTCARE_DB_HOST: str = "127.0.0.1"
    SMARTCARE_DB_PORT: int = 27017
    SMARTCARE_DB_USER: str = ""
    SMARTCARE_DB_PASSWORD: str = ""
    SMARTCARE_DB_AUTH: str = "admin"

    # DataCenter
    DATACENTER_DB_HOST: str = "127.0.0.1"
    DATACENTER_DB_PORT: int = 27017
    DATACENTER_DB_USER: str = ""
    DATACENTER_DB_PASSWORD: str = ""
    DATACENTER_DB_AUTH: str = "admin"

    # Redis
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""

    # LLM
    LLM_BASE_URL: str = "http://127.0.0.1:11434/v1"
    LLM_API_KEY: str = "ollama"
    LLM_MODEL: str = "qwen2.5:32b"

    # Security
    SECRET_KEY: str = "change-me-in-production"

    class Config:
        env_file = ".env"
        extra = "ignore"


class AppConfig:
    """应用配置：合并环境变量 + YAML"""

    def __init__(self):
        self.settings = Settings()
        self.yaml_cfg = self._load_yaml()

    def _load_yaml(self) -> dict:
        """加载 config.yaml"""
        # __file__ = backend/app/config.py
        # 往上两级 = backend/
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.yaml"
        )
        print(f"[CONFIG] 查找配置文件: {config_path}")
        print(f"[CONFIG] 文件存在: {os.path.exists(config_path)}")

        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
                if cfg:
                    print(f"[CONFIG] YAML顶层keys: {list(cfg.keys())}")
                    return cfg
                else:
                    print("[CONFIG] ⚠️ YAML文件为空!")
                    return {}

        print("[CONFIG] ⚠️ 配置文件不存在!")
        return {}

    def _build_mongo_uri(self, host, port, user, password, auth_db) -> str:
        """构建 MongoDB URI，自动对用户名密码做 URL 编码"""
        if user and password:
            encoded_user = quote_plus(str(user))
            encoded_pwd = quote_plus(str(password))
            return (
                f"mongodb://{encoded_user}:{encoded_pwd}"
                f"@{host}:{port}/?authSource={auth_db}"
            )
        else:
            # 无认证
            return f"mongodb://{host}:{port}/"

    @property
    def smartcare_uri(self) -> str:
        return self._build_mongo_uri(
            self.settings.SMARTCARE_DB_HOST,
            self.settings.SMARTCARE_DB_PORT,
            self.settings.SMARTCARE_DB_USER,
            self.settings.SMARTCARE_DB_PASSWORD,
            self.settings.SMARTCARE_DB_AUTH,
        )

    @property
    def datacenter_uri(self) -> str:
        return self._build_mongo_uri(
            self.settings.DATACENTER_DB_HOST,
            self.settings.DATACENTER_DB_PORT,
            self.settings.DATACENTER_DB_USER,
            self.settings.DATACENTER_DB_PASSWORD,
            self.settings.DATACENTER_DB_AUTH,
        )

    @property
    def redis_url(self) -> str:
        if self.settings.REDIS_PASSWORD:
            encoded_pwd = quote_plus(str(self.settings.REDIS_PASSWORD))
            return (
                f"redis://:{encoded_pwd}"
                f"@{self.settings.REDIS_HOST}:{self.settings.REDIS_PORT}/0"
            )
        return (
            f"redis://{self.settings.REDIS_HOST}:{self.settings.REDIS_PORT}/0"
        )


# 单例
_config = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = AppConfig()
    return _config
