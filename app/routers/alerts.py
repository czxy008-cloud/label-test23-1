"""
报警记录路由模块

提供报警记录查询和确认API端点。
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import (
    AlertAcknowledgeRequest,
    AlertListResponse,
    AlertQueryParams,
    AlertResponse,
)

router = APIRouter(prefix="/alerts", tags=["报警管理"])


@router.get(
    "",
    response_model=AlertListResponse,
    summary="查询报警记录",
    description="查询历史报警记录，支持按设备ID、报警类型、级别、时间范围等条件筛选",
)
async def query_alerts(
    device_id: Optional[str] = Query(default=None, description="设备ID"),
    alert_type: Optional[str] = Query(default=None, description="报警类型"),
    alert_level: Optional[str] = Query(default=None, description="报警级别"),
    is_acknowledged: Optional[bool] = Query(default=None, description="是否已确认"),
    start_time: Optional[datetime] = Query(default=None, description="开始时间"),
    end_time: Optional[datetime] = Query(default=None, description="结束时间"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
):
    """
    查询报警记录

    - **device_id**: 按设备ID筛选 (可选)
    - **alert_type**: 按报警类型筛选 (可选)
    - **alert_level**: 按报警级别筛选 (可选: info, warning, critical)
    - **is_acknowledged**: 按确认状态筛选 (可选)
    - **start_time**: 开始时间 (可选，ISO格式)
    - **end_time**: 结束时间 (可选，ISO格式)
    - **page**: 页码 (从1开始)
    - **page_size**: 每页条数 (最大100)
    """
    params = AlertQueryParams(
        device_id=device_id,
        alert_type=alert_type,
        alert_level=alert_level,
        is_acknowledged=is_acknowledged,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )

    alerts, total = await crud.query_alerts(db, params)

    return AlertListResponse(
        code=200,
        message="Success",
        total=total,
        page=page,
        page_size=page_size,
        data=[AlertResponse.from_orm(a) for a in alerts],
    )


@router.get(
    "/{alert_id}",
    response_model=AlertResponse,
    summary="获取报警详情",
    description="根据报警ID获取报警详细信息",
)
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    获取报警详情

    - **alert_id**: 报警ID
    """
    alert = await crud.get_alert_by_id(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return AlertResponse.from_orm(alert)


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertResponse,
    summary="确认报警",
    description="确认处理报警记录，标记为已确认状态",
)
async def acknowledge_alert(
    alert_id: int,
    request: AlertAcknowledgeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    确认报警

    - **alert_id**: 报警ID
    - **acknowledged_by**: 确认人名称
    """
    alert = await crud.get_alert_by_id(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.is_acknowledged:
        raise HTTPException(status_code=400, detail="Alert already acknowledged")

    updated_alert = await crud.acknowledge_alert(db, alert_id, request)

    return AlertResponse.from_orm(updated_alert)
