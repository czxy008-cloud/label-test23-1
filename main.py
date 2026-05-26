"""
智能家居设备状态监控 API 服务

FastAPI 应用入口文件，包含应用初始化和路由注册。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.redis import close_redis_connection
from app.routers import alerts, devices, status, thresholds

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    智能家居设备状态监控 API 服务

    ## 功能概述

    本服务提供智能家居设备的接入管理和状态监控功能：

    - **设备注册**: 为新设备生成唯一的 device_id 和 secret_key
    - **状态上报**: 接收设备上报的实时状态数据 (温度、湿度、开关状态等)
    - **阈值告警**: 当状态数据超出配置的阈值范围时自动触发报警
    - **历史查询**: 支持按设备ID和时间范围查询历史状态和报警记录

    ## 快速开始

    1. 调用 `POST /api/v1/devices/register` 注册设备，获取凭据
    2. 调用 `POST /api/v1/thresholds` 配置报警阈值 (可选)
    3. 调用 `POST /api/v1/status/report` 上报设备状态
    4. 调用 `GET /api/v1/alerts` 查看报警记录
    """,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化操作"""
    pass


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理操作"""
    await close_redis_connection()


@app.get(
    "/",
    tags=["系统"],
    summary="服务健康检查",
    description="检查API服务是否正常运行",
)
async def root():
    """
    健康检查接口

    返回服务基本信息。
    """
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
    }


app.include_router(devices.router, prefix=settings.API_V1_PREFIX)
app.include_router(status.router, prefix=settings.API_V1_PREFIX)
app.include_router(thresholds.router, prefix=settings.API_V1_PREFIX)
app.include_router(alerts.router, prefix=settings.API_V1_PREFIX)
