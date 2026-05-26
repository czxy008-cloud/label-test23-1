"""
状态上报路由模块

提供设备状态上报和历史数据查询API端点。
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.redis import cache_device_status
from app.schemas import (
    StatusListResponse,
    StatusQueryParams,
    StatusReportRequest,
    StatusReportResponse,
    StatusResponse,
)

router = APIRouter(prefix="/status", tags=["状态管理"])


@router.post(
    "/report",
    response_model=StatusReportResponse,
    summary="状态上报",
    description="设备上报实时状态数据，系统会自动检测阈值并触发报警",
)
async def report_status(
    request: StatusReportRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    设备状态上报接口

    - **device_id**: 设备ID
    - **secret_key**: 设备密钥 (用于身份验证)
    - **status_data**: 状态数据 (JSON格式，可包含任意键值对)

    示例 status_data:
    ```json
    {
        "temperature": 25.5,
        "humidity": 60.0,
        "power": "on",
        "battery_level": 85
    }
    ```
    """
    device = await crud.verify_device_credentials(
        db, request.device_id, request.secret_key
    )
    if not device:
        raise HTTPException(
            status_code=401,
            detail="Invalid device credentials or device not active",
        )

    status_record, triggered_alerts = await crud.report_device_status(
        db, device, request
    )

    await crud.update_device_last_seen(db, device)

    await cache_device_status(
        device_id=device.device_id,
        status_data=request.status_data,
        reported_at=status_record.reported_at.isoformat(),
        status_id=status_record.id,
        has_alert=status_record.has_alert,
    )

    return StatusReportResponse(
        code=201,
        message="Status reported successfully",
        data={
            "status_id": status_record.id,
            "reported_at": status_record.reported_at.isoformat(),
            "has_alert": status_record.has_alert,
            "alerts": triggered_alerts,
        },
    )


@router.get(
    "",
    response_model=StatusListResponse,
    summary="查询状态记录",
    description="查询设备状态历史记录，支持按设备ID、时间范围和报警状态筛选",
)
async def query_status(
    device_id: Optional[str] = Query(default=None, description="设备ID"),
    has_alert: Optional[bool] = Query(default=None, description="是否包含报警"),
    start_time: Optional[datetime] = Query(default=None, description="开始时间"),
    end_time: Optional[datetime] = Query(default=None, description="结束时间"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
):
    """
    查询设备状态记录

    - **device_id**: 按设备ID筛选 (可选)
    - **has_alert**: 按报警状态筛选 (可选)
    - **start_time**: 开始时间 (可选，ISO格式)
    - **end_time**: 结束时间 (可选，ISO格式)
    - **page**: 页码 (从1开始)
    - **page_size**: 每页条数 (最大100)
    """
    params = StatusQueryParams(
        device_id=device_id,
        has_alert=has_alert,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )

    status_records, total = await crud.query_device_status(db, params)

    return StatusListResponse(
        code=200,
        message="Success",
        total=total,
        page=page,
        page_size=page_size,
        data=[StatusResponse.from_orm(s) for s in status_records],
    )


@router.get(
    "/{device_id}/latest",
    response_model=StatusResponse,
    summary="获取最新状态",
    description="获取指定设备的最新状态记录，优先从Redis缓存读取，未命中时回源数据库",
)
async def get_latest_status(
    device_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    获取设备最新状态

    - **device_id**: 设备ID

    采用缓存优先策略: 先查 Redis 缓存，未命中再查询数据库并回填缓存。
    """
    device = await crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    latest_status = await crud.get_latest_device_status_cached(db, device_id)

    if not latest_status:
        raise HTTPException(status_code=404, detail="No status records found")

    return StatusResponse.from_orm(latest_status)
