"""
SQLAlchemy ORM 模型

定义数据库表对应的 Python 类，与 SQL 初始化脚本中的表结构对应。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class Device(Base):
    """设备注册表 ORM 模型"""

    __tablename__ = "devices"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="自增主键")
    device_id = Column(String(64), nullable=False, unique=True, comment="设备唯一标识符")
    device_name = Column(String(128), nullable=False, comment="设备名称")
    device_type = Column(String(64), nullable=False, comment="设备类型")
    secret_key = Column(String(128), nullable=False, comment="设备密钥")
    location = Column(String(256), nullable=True, comment="设备安装位置")
    description = Column(Text, nullable=True, comment="设备描述信息")
    is_active = Column(Boolean, nullable=False, server_default=text("true"), comment="是否激活")
    registered_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="注册时间"
    )
    last_seen_at = Column(DateTime, nullable=True, comment="最后在线时间")
    status = Column(
        String(16),
        nullable=False,
        server_default=text("'online'"),
        comment="设备在线状态: online/fault/alarm/offline",
    )
    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="更新时间",
    )

    status_records = relationship("DeviceStatus", back_populates="device", cascade="all, delete-orphan")
    threshold_configs = relationship("ThresholdConfig", back_populates="device", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="device", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_devices_device_id", "device_id"),
        Index("idx_devices_device_type", "device_type"),
        Index("idx_devices_is_active", "is_active"),
        Index("idx_devices_status", "status"),
    )


class ThresholdConfig(Base):
    """阈值配置表 ORM 模型"""

    __tablename__ = "threshold_configs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="自增主键")
    device_id = Column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的设备ID",
    )
    metric_name = Column(String(64), nullable=False, comment="监控指标名称")
    metric_unit = Column(String(32), nullable=True, comment="指标单位")
    min_value = Column(Double, nullable=True, comment="最小值阈值")
    max_value = Column(Double, nullable=True, comment="最大值阈值")
    is_enabled = Column(Boolean, nullable=False, server_default=text("true"), comment="是否启用")
    consecutive_count = Column(
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="连续N次超出阈值才触发报警 (防抖次数, 默认1即立即触发)",
    )
    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="更新时间",
    )

    device = relationship("Device", back_populates="threshold_configs")

    __table_args__ = (
        UniqueConstraint("device_id", "metric_name", name="uq_device_metric"),
        Index("idx_thresholds_device_id", "device_id"),
    )


class DeviceStatus(Base):
    """设备状态快照表 ORM 模型"""

    __tablename__ = "device_status"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="自增主键")
    device_id = Column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的设备ID",
    )
    status_data = Column(JSONB, nullable=False, comment="状态数据 (JSON)")
    has_alert = Column(Boolean, nullable=False, server_default=text("false"), comment="是否包含报警")
    reported_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="上报时间"
    )
    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )

    device = relationship("Device", back_populates="status_records")

    __table_args__ = (
        Index("idx_status_device_id", "device_id"),
        Index("idx_status_reported_at", "reported_at"),
        Index("idx_status_device_time", "device_id", "reported_at"),
        Index("idx_status_has_alert", "has_alert"),
        Index("idx_status_data_gin", "status_data", postgresql_using="gin"),
    )


class Alert(Base):
    """历史报警记录表 ORM 模型"""

    __tablename__ = "alerts"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="自增主键")
    device_id = Column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的设备ID",
    )
    alert_type = Column(String(64), nullable=False, comment="报警类型")
    alert_level = Column(String(16), nullable=False, server_default="warning", comment="报警级别")
    metric_name = Column(String(64), nullable=True, comment="触发报警的指标名称")
    metric_value = Column(Double, nullable=True, comment="触发报警时的指标值")
    threshold_min = Column(Double, nullable=True, comment="报警时的最小阈值")
    threshold_max = Column(Double, nullable=True, comment="报警时的最大阈值")
    alert_message = Column(Text, nullable=True, comment="报警详情描述")
    is_acknowledged = Column(Boolean, nullable=False, server_default=text("false"), comment="是否已确认")
    acknowledged_at = Column(DateTime, nullable=True, comment="确认时间")
    acknowledged_by = Column(String(128), nullable=True, comment="确认人")
    status_snapshot = Column(JSONB, nullable=True, comment="报警时的完整状态快照")
    reported_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="报警触发时间"
    )
    resolved_at = Column(DateTime, nullable=True, comment="报警解决时间")
    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )

    device = relationship("Device", back_populates="alerts")

    __table_args__ = (
        Index("idx_alerts_device_id", "device_id"),
        Index("idx_alerts_alert_type", "alert_type"),
        Index("idx_alerts_alert_level", "alert_level"),
        Index("idx_alerts_reported_at", "reported_at"),
        Index("idx_alerts_device_time", "device_id", "reported_at"),
        Index("idx_alerts_acknowledged", "is_acknowledged"),
    )
