"""
应用配置模块

负责从环境变量或 .env 文件中加载配置，提供统一的配置访问入口。
使用 pydantic BaseSettings 实现类型安全的配置管理。
"""

import os
from typing import Optional

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """应用全局配置"""

    APP_NAME: str = Field(default="Smart Home IoT API", description="应用名称")
    APP_VERSION: str = Field(default="1.0.0", description="应用版本")
    DEBUG: bool = Field(default=False, description="调试模式")

    # 数据库配置
    POSTGRES_HOST: str = Field(default="localhost", description="PostgreSQL 主机地址")
    POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL 端口")
    POSTGRES_USER: str = Field(default="postgres", description="PostgreSQL 用户名")
    POSTGRES_PASSWORD: str = Field(default="postgres", description="PostgreSQL 密码")
    POSTGRES_DB: str = Field(default="smart_home", description="PostgreSQL 数据库名")

    # Redis 缓存配置
    REDIS_HOST: str = Field(default="localhost", description="Redis 主机地址")
    REDIS_PORT: int = Field(default=6379, description="Redis 端口")
    REDIS_DB: int = Field(default=0, description="Redis 数据库编号")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis 密码")
    REDIS_STATUS_CACHE_TTL: int = Field(default=300, description="设备最新状态缓存过期时间 (秒)")
    REDIS_DEBOUNCE_WINDOW_TTL: int = Field(default=600, description="防抖计数窗口TTL (秒)")
    REDIS_MAX_CONNECTIONS: int = Field(default=20, description="Redis 连接池最大连接数")

    # API 配置
    API_V1_PREFIX: str = Field(default="/api/v1", description="API v1 路由前缀")

    # 设备注册配置
    DEVICE_ID_PREFIX: str = Field(default="dev", description="设备ID前缀")
    SECRET_KEY_LENGTH: int = Field(default=64, description="生成的密钥长度")

    # 分页配置
    DEFAULT_PAGE_SIZE: int = Field(default=20, description="默认每页条数")
    MAX_PAGE_SIZE: int = Field(default=100, description="最大每页条数")

    @property
    def DATABASE_URL(self) -> str:
        """构造数据库连接 URL"""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        """构造同步数据库连接 URL（用于 Alembic 等工具）"""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self) -> str:
        """构造 Redis 连接 URL"""
        if self.REDIS_PASSWORD:
            return (
                f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
            )
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
