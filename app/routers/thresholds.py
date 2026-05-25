"""
阈值配置路由模块

提供阈值配置的增删改查API端点。
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import (
    ResponseBase,
    ThresholdConfigListResponse,
    ThresholdConfigRequest,
    ThresholdConfigResponse,
    ThresholdConfigUpdateRequest,
)

router = APIRouter(prefix="/thresholds", tags=["阈值配置"])


@router.post(
    "",
    response_model=ResponseBase,
    summary="创建阈值配置",
    description="为设备创建报警阈值配置，当指标超出范围时自动触发报警",
)
async def create_threshold(
    request: ThresholdConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    创建阈值配置

    - **device_id**: 设备ID
    - **metric_name**: 监控指标名称 (如: temperature, humidity)
    - **metric_unit**: 指标单位 (如: °C, %, W)
    - **min_value**: 最小值阈值 (可选，低于此值触发报警)
    - **max_value**: 最大值阈值 (可选，高于此值触发报警)
    - **is_enabled**: 是否启用该阈值 (默认启用)
    """
    device = await crud.get_device_by_id(db, request.device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    config = await crud.create_threshold_config(db, request)
    if not config:
        raise HTTPException(
            status_code=400,
            detail="Failed to create threshold config. Check for duplicate device_id + metric_name.",
        )

    return ResponseBase(
        code=201,
        message="Threshold config created successfully",
    )


@router.get(
    "/{device_id}",
    response_model=ThresholdConfigListResponse,
    summary="获取设备阈值配置",
    description="获取指定设备的所有阈值配置",
)
async def get_device_thresholds(
    device_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    获取设备阈值配置

    - **device_id**: 设备ID
    """
    device = await crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    configs = await crud.get_threshold_configs_by_device(db, device_id)

    return ThresholdConfigListResponse(
        code=200,
        message="Success",
        data=[ThresholdConfigResponse.from_orm(c) for c in configs],
    )


@router.put(
    "/{config_id}",
    response_model=ThresholdConfigResponse,
    summary="更新阈值配置",
    description="更新指定阈值配置的参数",
)
async def update_threshold(
    config_id: int,
    request: ThresholdConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    更新阈值配置

    - **config_id**: 配置ID
    - **metric_unit**: 指标单位 (可选)
    - **min_value**: 最小值阈值 (可选)
    - **max_value**: 最大值阈值 (可选)
    - **is_enabled**: 是否启用 (可选)
    """
    config = await crud.update_threshold_config(db, config_id, request)
    if not config:
        raise HTTPException(status_code=404, detail="Threshold config not found")

    return ThresholdConfigResponse.from_orm(config)


@router.delete(
    "/{config_id}",
    response_model=ResponseBase,
    summary="删除阈值配置",
    description="删除指定的阈值配置",
)
async def delete_threshold(
    config_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    删除阈值配置

    - **config_id**: 配置ID
    """
    success = await crud.delete_threshold_config(db, config_id)
    if not success:
        raise HTTPException(status_code=404, detail="Threshold config not found")

    return ResponseBase(
        code=200,
        message="Threshold config deleted successfully",
    )
