"""
设备管理路由模块

提供设备注册、查询等API端点。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import (
    DeviceListResponse,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    DeviceResponse,
    PaginationParams,
)

router = APIRouter(prefix="/devices", tags=["设备管理"])


@router.post(
    "/register",
    response_model=DeviceRegisterResponse,
    summary="设备注册",
    description="注册新设备，返回唯一的device_id和secret_key",
)
async def register_device(
    request: DeviceRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    设备注册接口

    - **device_name**: 设备名称
    - **device_type**: 设备类型 (如: sensor, switch, camera)
    - **location**: 设备位置 (可选)
    - **description**: 设备描述 (可选)

    返回唯一的 device_id 和 secret_key，请妥善保存 secret_key，
    后续状态上报时需要使用。
    """
    device, secret_key = await crud.create_device(db, request)

    return DeviceRegisterResponse(
        code=201,
        message="Device registered successfully",
        data={
            "device_id": device.device_id,
            "secret_key": secret_key,
            "device_name": device.device_name,
        },
    )


@router.get(
    "",
    response_model=DeviceListResponse,
    summary="获取设备列表",
    description="分页获取所有设备列表，支持按设备类型和激活状态筛选",
)
async def list_devices(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    device_type: Optional[str] = Query(default=None, description="设备类型筛选"),
    is_active: Optional[bool] = Query(default=None, description="激活状态筛选"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取设备列表

    - **page**: 页码 (从1开始)
    - **page_size**: 每页条数 (最大100)
    - **device_type**: 按设备类型筛选 (可选)
    - **is_active**: 按激活状态筛选 (可选)
    """
    devices, total = await crud.list_devices(
        db=db,
        page=page,
        page_size=page_size,
        device_type=device_type,
        is_active=is_active,
    )

    return DeviceListResponse(
        code=200,
        message="Success",
        total=total,
        page=page,
        page_size=page_size,
        data=[DeviceResponse.from_orm(d) for d in devices],
    )


@router.get(
    "/{device_id}",
    response_model=DeviceResponse,
    summary="获取设备详情",
    description="根据设备ID获取设备详细信息",
)
async def get_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    获取设备详情

    - **device_id**: 设备唯一标识符
    """
    device = await crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return DeviceResponse.from_orm(device)
