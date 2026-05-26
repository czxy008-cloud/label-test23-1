"""
Pydantic 数据模型（Schema）

定义 API 请求和响应的数据结构，用于数据校验和序列化。
包含设备注册、状态上报、阈值配置、报警记录等相关模型。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


# ============================================================
# 通用响应模型
# ============================================================

class ResponseBase(BaseModel):
    """通用响应基类"""
    code: int = Field(default=200, description="状态码")
    message: str = Field(default="success", description="响应消息")


class PaginatedResponse(ResponseBase):
    """分页响应基类"""
    total: int = Field(default=0, description="总记录数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=20, description="每页条数")
    data: List[Any] = Field(default_factory=list, description="数据列表")


# ============================================================
# 设备注册相关模型
# ============================================================

class DeviceRegisterRequest(BaseModel):
    """设备注册请求模型"""
    device_name: str = Field(..., min_length=1, max_length=128, description="设备名称")
    device_type: str = Field(..., min_length=1, max_length=64, description="设备类型")
    location: Optional[str] = Field(default=None, max_length=256, description="设备位置")
    description: Optional[str] = Field(default=None, description="设备描述")


class DeviceRegisterResponse(ResponseBase):
    """设备注册响应模型"""
    data: Dict[str, str] = Field(
        ...,
        description="设备凭据信息",
        example={
            "device_id": "dev-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "secret_key": "sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "device_name": "客厅温湿度传感器",
        },
    )


class DeviceResponse(BaseModel):
    """设备信息响应模型"""
    id: int
    device_id: str
    device_name: str
    device_type: str
    location: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    registered_at: datetime
    last_seen_at: Optional[datetime] = None
    status: str = "online"
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class DeviceListResponse(PaginatedResponse):
    """设备列表响应模型"""
    data: List[DeviceResponse] = Field(default_factory=list)


# ============================================================
# 状态上报相关模型
# ============================================================

class StatusReportRequest(BaseModel):
    """状态上报请求模型"""
    device_id: str = Field(..., min_length=1, max_length=64, description="设备ID")
    secret_key: str = Field(..., min_length=1, max_length=128, description="设备密钥")
    status_data: Dict[str, Any] = Field(
        ...,
        description="状态数据 (JSON格式)",
        example={
            "temperature": 25.5,
            "humidity": 60.0,
            "power": "on",
            "battery_level": 85,
        },
    )

    @validator("status_data")
    @classmethod
    def validate_status_data_not_empty(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """校验状态数据不为空"""
        if not v:
            raise ValueError("status_data cannot be empty")
        return v


class StatusReportResponse(ResponseBase):
    """状态上报响应模型"""
    data: Dict[str, Any] = Field(
        ...,
        description="上报结果",
        example={
            "status_id": 123,
            "reported_at": "2024-01-01T12:00:00",
            "has_alert": False,
            "alerts": [],
        },
    )


class StatusResponse(BaseModel):
    """设备状态记录响应模型"""
    id: int
    device_id: str
    status_data: Dict[str, Any]
    has_alert: bool
    reported_at: datetime
    created_at: datetime

    class Config:
        orm_mode = True


class StatusListResponse(PaginatedResponse):
    """状态列表响应模型"""
    data: List[StatusResponse] = Field(default_factory=list)


# ============================================================
# 阈值配置相关模型
# ============================================================

class ThresholdConfigRequest(BaseModel):
    """阈值配置请求模型"""
    device_id: str = Field(..., min_length=1, max_length=64, description="设备ID")
    metric_name: str = Field(..., min_length=1, max_length=64, description="监控指标名称")
    metric_unit: Optional[str] = Field(default=None, max_length=32, description="指标单位")
    min_value: Optional[float] = Field(default=None, description="最小值阈值")
    max_value: Optional[float] = Field(default=None, description="最大值阈值")
    is_enabled: bool = Field(default=True, description="是否启用")
    consecutive_count: int = Field(
        default=1,
        ge=1,
        le=100,
        description="连续N次超出阈值才触发报警 (防抖次数, 1=立即触发)",
    )

    @validator("max_value")
    @classmethod
    def validate_max_value(cls, v: Optional[float], values: dict) -> Optional[float]:
        """校验最大值不小于最小值"""
        if v is not None and values.get("min_value") is not None:
            if v < values["min_value"]:
                raise ValueError("max_value must be greater than or equal to min_value")
        return v


class ThresholdConfigUpdateRequest(BaseModel):
    """阈值配置更新请求模型"""
    metric_unit: Optional[str] = Field(default=None, max_length=32, description="指标单位")
    min_value: Optional[float] = Field(default=None, description="最小值阈值")
    max_value: Optional[float] = Field(default=None, description="最大值阈值")
    is_enabled: Optional[bool] = Field(default=None, description="是否启用")
    consecutive_count: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="连续N次超出阈值才触发报警 (防抖次数, 1=立即触发)",
    )


class ThresholdConfigResponse(BaseModel):
    """阈值配置响应模型"""
    id: int
    device_id: str
    metric_name: str
    metric_unit: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    is_enabled: bool
    consecutive_count: int = 1
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class ThresholdConfigListResponse(ResponseBase):
    """阈值配置列表响应模型"""
    data: List[ThresholdConfigResponse] = Field(default_factory=list)


# ============================================================
# 报警记录相关模型
# ============================================================

class AlertResponse(BaseModel):
    """报警记录响应模型"""
    id: int
    device_id: str
    alert_type: str
    alert_level: str
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    threshold_min: Optional[float] = None
    threshold_max: Optional[float] = None
    alert_message: Optional[str] = None
    is_acknowledged: bool
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    status_snapshot: Optional[Dict[str, Any]] = None
    reported_at: datetime
    resolved_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        orm_mode = True


class AlertListResponse(PaginatedResponse):
    """报警记录列表响应模型"""
    data: List[AlertResponse] = Field(default_factory=list)


class AlertAcknowledgeRequest(BaseModel):
    """报警确认请求模型"""
    acknowledged_by: str = Field(..., min_length=1, max_length=128, description="确认人")


# ============================================================
# 查询参数模型
# ============================================================

class PaginationParams(BaseModel):
    """分页查询参数"""
    page: int = Field(default=1, ge=1, description="页码 (从1开始)")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数")


class TimeRangeParams(BaseModel):
    """时间范围查询参数"""
    start_time: Optional[datetime] = Field(default=None, description="开始时间")
    end_time: Optional[datetime] = Field(default=None, description="结束时间")

    @validator("end_time")
    @classmethod
    def validate_time_range(cls, v: Optional[datetime], values: dict) -> Optional[datetime]:
        """校验结束时间不早于开始时间"""
        if v is not None and values.get("start_time") is not None:
            if v < values["start_time"]:
                raise ValueError("end_time must be after start_time")
        return v


class StatusQueryParams(TimeRangeParams, PaginationParams):
    """状态查询参数 (继承时间范围和分页)"""
    device_id: Optional[str] = Field(default=None, description="设备ID")
    has_alert: Optional[bool] = Field(default=None, description="是否包含报警")


class AlertQueryParams(TimeRangeParams, PaginationParams):
    """报警查询参数 (继承时间范围和分页)"""
    device_id: Optional[str] = Field(default=None, description="设备ID")
    alert_type: Optional[str] = Field(default=None, description="报警类型")
    alert_level: Optional[str] = Field(default=None, description="报警级别")
    is_acknowledged: Optional[bool] = Field(default=None, description="是否已确认")
