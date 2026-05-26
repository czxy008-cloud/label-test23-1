"""
业务逻辑层 (CRUD)

封装所有数据库操作逻辑，包括设备注册、状态上报、阈值配置、报警查询等。
"""

import secrets
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import Alert, Device, DeviceStatus, ThresholdConfig
from app.redis import (
    cache_device_status,
    get_cached_device_status,
    increment_exceed_count,
    reset_exceed_count,
)
from app.schemas import (
    AlertQueryParams,
    AlertAcknowledgeRequest,
    DeviceRegisterRequest,
    StatusQueryParams,
    StatusReportRequest,
    ThresholdConfigRequest,
    ThresholdConfigUpdateRequest,
)


# ============================================================
# 工具函数
# ============================================================

def generate_device_id() -> str:
    """
    生成唯一的设备ID

    Returns:
        str: 格式为 {prefix}-{uuid} 的设备ID
    """
    return f"{settings.DEVICE_ID_PREFIX}-{uuid.uuid4().hex}"


def generate_secret_key() -> str:
    """
    生成安全的设备密钥

    Returns:
        str: 随机生成的密钥字符串
    """
    return f"sk_{secrets.token_hex(settings.SECRET_KEY_LENGTH // 2)}"


async def check_thresholds(
    device_id: str,
    status_data: Dict[str, Any],
    threshold_configs: List[ThresholdConfig],
) -> List[Dict[str, Any]]:
    """
    检查状态数据是否触发阈值报警 (含防抖逻辑)

    对于每个启用的阈值配置:
    1. 判断指标值是否超出 [min, max] 范围
    2. 若超出，递增 Redis 中的连续超出计数 (带TTL窗口)
    3. 若连续计数达到配置的 consecutive_count，才真正触发报警
    4. 若恢复到正常范围，重置连续计数

    Args:
        device_id: 设备ID (用于构建Redis计数键)
        status_data: 设备上报的状态数据
        threshold_configs: 阈值配置列表

    Returns:
        List[Dict]: 触发的报警列表，每个报警包含详细信息
    """
    alerts = []

    for config in threshold_configs:
        if not config.is_enabled:
            continue

        metric_name = config.metric_name
        if metric_name not in status_data:
            continue

        metric_value = status_data[metric_name]

        if not isinstance(metric_value, (int, float)):
            continue

        is_alert = False
        alert_type = ""

        if config.min_value is not None and metric_value < config.min_value:
            is_alert = True
            alert_type = f"low_{metric_name}"
        elif config.max_value is not None and metric_value > config.max_value:
            is_alert = True
            alert_type = f"high_{metric_name}"

        if is_alert:
            current_count = await increment_exceed_count(device_id, metric_name)
            required_count = max(1, config.consecutive_count or 1)

            if current_count >= required_count:
                alerts.append(
                    {
                        "alert_type": alert_type,
                        "alert_level": "warning",
                        "metric_name": metric_name,
                        "metric_value": metric_value,
                        "threshold_min": config.min_value,
                        "threshold_max": config.max_value,
                        "alert_message": (
                            f"{metric_name} 值 {metric_value}{config.metric_unit or ''} "
                            f"超出阈值范围 "
                            f"[{config.min_value}, {config.max_value}] "
                            f"(连续{current_count}次超出)"
                        ),
                    }
                )
        else:
            await reset_exceed_count(device_id, metric_name)

    return alerts


# ============================================================
# 设备相关 CRUD 操作
# ============================================================

async def create_device(
    db: AsyncSession,
    request: DeviceRegisterRequest,
) -> Tuple[Device, str]:
    """
    注册新设备

    Args:
        db: 数据库会话
        request: 设备注册请求数据

    Returns:
        Tuple[Device, str]: (设备对象, 生成的密钥)
    """
    device_id = generate_device_id()
    secret_key = generate_secret_key()

    device = Device(
        device_id=device_id,
        device_name=request.device_name,
        device_type=request.device_type,
        secret_key=secret_key,
        location=request.location,
        description=request.description,
    )

    db.add(device)
    await db.flush()

    return device, secret_key


async def get_device_by_id(db: AsyncSession, device_id: str) -> Optional[Device]:
    """
    根据设备ID获取设备信息

    Args:
        db: 数据库会话
        device_id: 设备ID

    Returns:
        Optional[Device]: 设备对象或None
    """
    result = await db.execute(
        select(Device).where(Device.device_id == device_id)
    )
    return result.scalar_one_or_none()


async def verify_device_credentials(
    db: AsyncSession,
    device_id: str,
    secret_key: str,
) -> Optional[Device]:
    """
    验证设备凭据

    Args:
        db: 数据库会话
        device_id: 设备ID
        secret_key: 设备密钥

    Returns:
        Optional[Device]: 验证通过返回设备对象，否则返回None
    """
    result = await db.execute(
        select(Device).where(
            and_(
                Device.device_id == device_id,
                Device.secret_key == secret_key,
                Device.is_active.is_(True),
            )
        )
    )
    return result.scalar_one_or_none()


async def update_device_last_seen(db: AsyncSession, device: Device) -> None:
    """
    更新设备最后在线时间

    Args:
        db: 数据库会话
        device: 设备对象
    """
    device.last_seen_at = datetime.utcnow()
    await db.flush()


async def mark_device_status(db: AsyncSession, device: Device, status: str) -> None:
    """
    更新设备在线状态 (如: online/fault/alarm/offline)

    当检测到报警时自动标记为 "alarm"，当恢复正常时标记为 "online"。
    状态变更会自动更新 last_seen_at 以反映最近活动时间。

    Args:
        db: 数据库会话
        device: 设备对象
        status: 新状态值 (online/fault/alarm/offline)
    """
    device.status = status
    device.last_seen_at = datetime.utcnow()
    await db.flush()


async def list_devices(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    device_type: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Tuple[List[Device], int]:
    """
    获取设备列表（分页）

    Args:
        db: 数据库会话
        page: 页码
        page_size: 每页条数
        device_type: 设备类型筛选
        is_active: 激活状态筛选

    Returns:
        Tuple[List[Device], int]: (设备列表, 总记录数)
    """
    query = select(Device)

    if device_type:
        query = query.where(Device.device_type == device_type)
    if is_active is not None:
        query = query.where(Device.is_active == is_active)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = (
        query
        .order_by(desc(Device.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(query)
    devices = result.scalars().all()

    return list(devices), total


# ============================================================
# 状态上报相关 CRUD 操作
# ============================================================

async def report_device_status(
    db: AsyncSession,
    device: Device,
    request: StatusReportRequest,
) -> Tuple[DeviceStatus, List[Dict[str, Any]]]:
    """
    处理设备状态上报

    包含以下步骤:
    1. 查询设备的启用阈值配置
    2. 调用带防抖的阈值检查函数 check_thresholds
    3. 写入设备状态快照
    4. 若触发报警，写入历史报警记录
    5. 若触发报警，自动将设备状态标记为"alarm"

    Args:
        db: 数据库会话
        device: 设备对象
        request: 状态上报请求

    Returns:
        Tuple[DeviceStatus, List[Dict]]: (状态记录, 触发的报警列表)
    """
    threshold_result = await db.execute(
        select(ThresholdConfig).where(
            and_(
                ThresholdConfig.device_id == device.device_id,
                ThresholdConfig.is_enabled.is_(True),
            )
        )
    )
    threshold_configs = list(threshold_result.scalars().all())

    triggered_alerts = await check_thresholds(
        device_id=device.device_id,
        status_data=request.status_data,
        threshold_configs=threshold_configs,
    )

    status_record = DeviceStatus(
        device_id=device.device_id,
        status_data=request.status_data,
        has_alert=len(triggered_alerts) > 0,
    )

    db.add(status_record)
    await db.flush()

    if triggered_alerts:
        for alert_data in triggered_alerts:
            alert = Alert(
                device_id=device.device_id,
                alert_type=alert_data["alert_type"],
                alert_level=alert_data["alert_level"],
                metric_name=alert_data["metric_name"],
                metric_value=alert_data["metric_value"],
                threshold_min=alert_data["threshold_min"],
                threshold_max=alert_data["threshold_max"],
                alert_message=alert_data["alert_message"],
                status_snapshot=request.status_data,
            )
            db.add(alert)
        await db.flush()

        await mark_device_status(db, device, "alarm")
    else:
        await mark_device_status(db, device, "online")

    return status_record, triggered_alerts


async def query_device_status(
    db: AsyncSession,
    params: StatusQueryParams,
) -> Tuple[List[DeviceStatus], int]:
    """
    查询设备状态记录

    Args:
        db: 数据库会话
        params: 查询参数

    Returns:
        Tuple[List[DeviceStatus], int]: (状态记录列表, 总记录数)
    """
    query = select(DeviceStatus)

    if params.device_id:
        query = query.where(DeviceStatus.device_id == params.device_id)
    if params.has_alert is not None:
        query = query.where(DeviceStatus.has_alert == params.has_alert)
    if params.start_time:
        query = query.where(DeviceStatus.reported_at >= params.start_time)
    if params.end_time:
        query = query.where(DeviceStatus.reported_at <= params.end_time)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = (
        query
        .order_by(desc(DeviceStatus.reported_at))
        .offset((params.page - 1) * params.page_size)
        .limit(params.page_size)
    )

    result = await db.execute(query)
    status_records = result.scalars().all()

    return list(status_records), total


# ============================================================
# 阈值配置相关 CRUD 操作
# ============================================================

async def create_threshold_config(
    db: AsyncSession,
    request: ThresholdConfigRequest,
) -> Optional[ThresholdConfig]:
    """
    创建阈值配置

    Args:
        db: 数据库会话
        request: 阈值配置请求

    Returns:
        Optional[ThresholdConfig]: 配置对象或None (如果设备不存在)
    """
    device = await get_device_by_id(db, request.device_id)
    if not device:
        return None

    config = ThresholdConfig(
        device_id=request.device_id,
        metric_name=request.metric_name,
        metric_unit=request.metric_unit,
        min_value=request.min_value,
        max_value=request.max_value,
        is_enabled=request.is_enabled,
        consecutive_count=request.consecutive_count,
    )

    db.add(config)
    await db.flush()

    return config


async def get_threshold_configs_by_device(
    db: AsyncSession,
    device_id: str,
) -> List[ThresholdConfig]:
    """
    获取设备的所有阈值配置

    Args:
        db: 数据库会话
        device_id: 设备ID

    Returns:
        List[ThresholdConfig]: 阈值配置列表
    """
    result = await db.execute(
        select(ThresholdConfig)
        .where(ThresholdConfig.device_id == device_id)
        .order_by(ThresholdConfig.metric_name)
    )
    return list(result.scalars().all())


async def update_threshold_config(
    db: AsyncSession,
    config_id: int,
    request: ThresholdConfigUpdateRequest,
) -> Optional[ThresholdConfig]:
    """
    更新阈值配置

    Args:
        db: 数据库会话
        config_id: 配置ID
        request: 更新请求

    Returns:
        Optional[ThresholdConfig]: 更新后的配置对象或None
    """
    result = await db.execute(
        select(ThresholdConfig).where(ThresholdConfig.id == config_id)
    )
    config = result.scalar_one_or_none()

    if not config:
        return None

    update_data = request.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)

    await db.flush()
    return config


async def delete_threshold_config(
    db: AsyncSession,
    config_id: int,
) -> bool:
    """
    删除阈值配置

    Args:
        db: 数据库会话
        config_id: 配置ID

    Returns:
        bool: 是否删除成功
    """
    result = await db.execute(
        select(ThresholdConfig).where(ThresholdConfig.id == config_id)
    )
    config = result.scalar_one_or_none()

    if not config:
        return False

    await db.delete(config)
    await db.flush()
    return True


# ============================================================
# 报警记录相关 CRUD 操作
# ============================================================

async def query_alerts(
    db: AsyncSession,
    params: AlertQueryParams,
) -> Tuple[List[Alert], int]:
    """
    查询报警记录

    Args:
        db: 数据库会话
        params: 查询参数

    Returns:
        Tuple[List[Alert], int]: (报警记录列表, 总记录数)
    """
    query = select(Alert)

    if params.device_id:
        query = query.where(Alert.device_id == params.device_id)
    if params.alert_type:
        query = query.where(Alert.alert_type == params.alert_type)
    if params.alert_level:
        query = query.where(Alert.alert_level == params.alert_level)
    if params.is_acknowledged is not None:
        query = query.where(Alert.is_acknowledged == params.is_acknowledged)
    if params.start_time:
        query = query.where(Alert.reported_at >= params.start_time)
    if params.end_time:
        query = query.where(Alert.reported_at <= params.end_time)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = (
        query
        .order_by(desc(Alert.reported_at))
        .offset((params.page - 1) * params.page_size)
        .limit(params.page_size)
    )

    result = await db.execute(query)
    alerts = result.scalars().all()

    return list(alerts), total


async def acknowledge_alert(
    db: AsyncSession,
    alert_id: int,
    request: AlertAcknowledgeRequest,
) -> Optional[Alert]:
    """
    确认报警

    Args:
        db: 数据库会话
        alert_id: 报警ID
        request: 确认请求

    Returns:
        Optional[Alert]: 更新后的报警对象或None
    """
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()

    if not alert:
        return None

    alert.is_acknowledged = True
    alert.acknowledged_at = datetime.utcnow()
    alert.acknowledged_by = request.acknowledged_by

    await db.flush()
    return alert


async def get_alert_by_id(
    db: AsyncSession,
    alert_id: int,
) -> Optional[Alert]:
    """
    根据ID获取报警记录

    Args:
        db: 数据库会话
        alert_id: 报警ID

    Returns:
        Optional[Alert]: 报警对象或None
    """
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    return result.scalar_one_or_none()


# ============================================================
# Redis 缓存相关操作
# ============================================================

async def get_latest_device_status_cached(
    db: AsyncSession,
    device_id: str,
) -> Optional[DeviceStatus]:
    """
    获取设备最新状态（先查缓存，未命中再回源数据库）

    策略:
    1. 优先从 Redis 缓存读取最新状态快照
    2. 缓存未命中时查询数据库获取最新一条记录
    3. 数据库命中后将结果回填到 Redis 缓存

    Args:
        db: 数据库会话
        device_id: 设备ID

    Returns:
        Optional[DeviceStatus]: 最新状态记录或None
    """
    cached = await get_cached_device_status(device_id)
    if cached is not None:
        return DeviceStatus(
            id=cached.get("status_id"),
            device_id=cached["device_id"],
            status_data=cached["status_data"],
            has_alert=cached.get("has_alert", False),
            reported_at=datetime.fromisoformat(cached["reported_at"]),
            created_at=datetime.fromisoformat(cached["reported_at"]),
        )

    params = StatusQueryParams(
        device_id=device_id,
        page=1,
        page_size=1,
    )
    status_records, _ = await query_device_status(db, params)

    if status_records:
        latest = status_records[0]
        await cache_device_status(
            device_id=device_id,
            status_data=latest.status_data,
            reported_at=latest.reported_at.isoformat(),
            status_id=latest.id,
            has_alert=latest.has_alert,
        )
        return latest

    return None
