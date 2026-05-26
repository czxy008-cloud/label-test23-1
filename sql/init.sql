-- ============================================================
-- 智能家居设备状态监控系统 - 数据库初始化脚本
-- 数据库: PostgreSQL 12+
-- 说明: 创建设备注册、状态快照、报警记录、阈值配置等表
-- ============================================================

-- -----------------------------------------------------------
-- 1. 设备注册表: 存储所有接入设备的基本信息与认证凭据
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id              BIGSERIAL       PRIMARY KEY,                        -- 自增主键
    device_id       VARCHAR(64)     NOT NULL UNIQUE,                    -- 设备唯一标识符 (UUID格式)
    device_name     VARCHAR(128)    NOT NULL,                           -- 设备名称
    device_type     VARCHAR(64)     NOT NULL,                           -- 设备类型 (如: sensor, switch, camera)
    secret_key      VARCHAR(128)    NOT NULL,                           -- 设备密钥 (用于状态上报时的认证)
    location        VARCHAR(256)    DEFAULT NULL,                       -- 设备安装位置
    description     TEXT            DEFAULT NULL,                       -- 设备描述信息
    is_active       BOOLEAN         DEFAULT TRUE,                       -- 设备是否激活
    registered_at   TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 注册时间
    last_seen_at    TIMESTAMP       DEFAULT NULL,                       -- 最后一次在线时间
    status          VARCHAR(16)     NOT NULL DEFAULT 'online',          -- 设备在线状态 (online/fault/alarm/offline)
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 记录创建时间
    updated_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP  -- 记录更新时间
);

-- 为 device_id 创建索引，加速查询
CREATE INDEX IF NOT EXISTS idx_devices_device_id ON devices(device_id);

-- 为 device_type 创建索引，支持按设备类型筛选
CREATE INDEX IF NOT EXISTS idx_devices_device_type ON devices(device_type);

-- 为 is_active 创建索引，支持按激活状态筛选
CREATE INDEX IF NOT EXISTS idx_devices_is_active ON devices(is_active);

-- 为 status 创建索引，支持按设备在线状态筛选
CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status);

-- -----------------------------------------------------------
-- 2. 阈值配置表: 存储各设备的报警阈值配置
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS threshold_configs (
    id              BIGSERIAL       PRIMARY KEY,                        -- 自增主键
    device_id       VARCHAR(64)     NOT NULL,                           -- 关联的设备ID
    metric_name     VARCHAR(64)     NOT NULL,                           -- 监控指标名称 (如: temperature, humidity, power)
    metric_unit     VARCHAR(32)     DEFAULT NULL,                       -- 指标单位 (如: °C, %, W)
    min_value       DOUBLE PRECISION DEFAULT NULL,                      -- 最小值阈值 (低于此值触发报警)
    max_value       DOUBLE PRECISION DEFAULT NULL,                      -- 最大值阈值 (高于此值触发报警)
    is_enabled      BOOLEAN         DEFAULT TRUE,                       -- 该阈值是否启用
    consecutive_count INTEGER         DEFAULT 1,                          -- 连续N次超出阈值才触发报警 (防抖次数, 1=立即触发)
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 配置创建时间
    updated_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 配置更新时间
    -- 约束: 同一设备的同一指标只能有一条配置
    CONSTRAINT uq_device_metric UNIQUE (device_id, metric_name),
    -- 外键约束: 关联设备注册表
    CONSTRAINT fk_threshold_device
        FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);

-- 为 device_id 创建索引，加速按设备查询阈值配置
CREATE INDEX IF NOT EXISTS idx_thresholds_device_id ON threshold_configs(device_id);

-- -----------------------------------------------------------
-- 3. 设备状态快照表: 存储设备上报的实时状态数据
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_status (
    id              BIGSERIAL       PRIMARY KEY,                        -- 自增主键
    device_id       VARCHAR(64)     NOT NULL,                           -- 关联的设备ID
    status_data     JSONB           NOT NULL,                           -- 状态数据 (JSON格式存储温度、湿度、开关状态等)
    has_alert       BOOLEAN         DEFAULT FALSE,                      -- 是否包含报警状态
    reported_at     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 状态上报时间
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 记录创建时间
    -- 外键约束: 关联设备注册表
    CONSTRAINT fk_status_device
        FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);

-- 为 device_id 创建索引，加速按设备查询状态
CREATE INDEX IF NOT EXISTS idx_status_device_id ON device_status(device_id);

-- 为 reported_at 创建索引，支持按时间范围查询
CREATE INDEX IF NOT EXISTS idx_status_reported_at ON device_status(reported_at);

-- 为 (device_id, reported_at) 创建复合索引，优化按设备+时间范围查询
CREATE INDEX IF NOT EXISTS idx_status_device_time ON device_status(device_id, reported_at);

-- 为 has_alert 创建索引，支持快速筛选报警状态
CREATE INDEX IF NOT EXISTS idx_status_has_alert ON device_status(has_alert);

-- 使用 GIN 索引加速 JSONB 字段内的键值查询
CREATE INDEX IF NOT EXISTS idx_status_data_gin ON device_status USING GIN (status_data);

-- -----------------------------------------------------------
-- 4. 历史报警记录表: 存储所有触发的报警记录
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id              BIGSERIAL       PRIMARY KEY,                        -- 自增主键
    device_id       VARCHAR(64)     NOT NULL,                           -- 关联的设备ID
    alert_type      VARCHAR(64)     NOT NULL,                           -- 报警类型 (如: high_temperature, low_humidity, offline)
    alert_level     VARCHAR(16)     NOT NULL DEFAULT 'warning',         -- 报警级别 (info, warning, critical)
    metric_name     VARCHAR(64)     DEFAULT NULL,                       -- 触发报警的指标名称
    metric_value    DOUBLE PRECISION DEFAULT NULL,                      -- 触发报警时的指标值
    threshold_min   DOUBLE PRECISION DEFAULT NULL,                      -- 报警时的最小阈值
    threshold_max   DOUBLE PRECISION DEFAULT NULL,                      -- 报警时的最大阈值
    alert_message   TEXT            DEFAULT NULL,                       -- 报警详情描述
    is_acknowledged BOOLEAN         DEFAULT FALSE,                      -- 是否已确认
    acknowledged_at TIMESTAMP       DEFAULT NULL,                       -- 确认时间
    acknowledged_by VARCHAR(128)    DEFAULT NULL,                       -- 确认人
    status_snapshot JSONB           DEFAULT NULL,                       -- 报警时的完整状态快照
    reported_at     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 报警触发时间
    resolved_at     TIMESTAMP       DEFAULT NULL,                       -- 报警解决时间
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 记录创建时间
    -- 外键约束: 关联设备注册表
    CONSTRAINT fk_alerts_device
        FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);

-- 为 device_id 创建索引，加速按设备查询报警
CREATE INDEX IF NOT EXISTS idx_alerts_device_id ON alerts(device_id);

-- 为 alert_type 创建索引，支持按报警类型筛选
CREATE INDEX IF NOT EXISTS idx_alerts_alert_type ON alerts(alert_type);

-- 为 alert_level 创建索引，支持按报警级别筛选
CREATE INDEX IF NOT EXISTS idx_alerts_alert_level ON alerts(alert_level);

-- 为 reported_at 创建索引，支持按时间范围查询报警
CREATE INDEX IF NOT EXISTS idx_alerts_reported_at ON alerts(reported_at);

-- 为 (device_id, reported_at) 创建复合索引，优化按设备+时间范围查询
CREATE INDEX IF NOT EXISTS idx_alerts_device_time ON alerts(device_id, reported_at);

-- 为 is_acknowledged 创建索引，支持筛选未确认报警
CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged ON alerts(is_acknowledged);

-- -----------------------------------------------------------
-- 5. 创建自动更新 updated_at 字段的触发器函数
-- -----------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 为 devices 表添加触发器
DROP TRIGGER IF EXISTS trg_devices_updated_at ON devices;
CREATE TRIGGER trg_devices_updated_at
    BEFORE UPDATE ON devices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 为 threshold_configs 表添加触发器
DROP TRIGGER IF EXISTS trg_thresholds_updated_at ON threshold_configs;
CREATE TRIGGER trg_thresholds_updated_at
    BEFORE UPDATE ON threshold_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- -----------------------------------------------------------
-- 6. 插入示例数据 (可选, 用于测试)
-- -----------------------------------------------------------
-- 注: 以下示例数据中的 secret_key 仅用于测试，生产环境应使用安全的随机生成方式

-- 示例设备1: 温湿度传感器
-- INSERT INTO devices (device_id, device_name, device_type, secret_key, location, description)
-- VALUES (
--     'dev-001-sensor-temp-hum-001',
--     '客厅温湿度传感器',
--     'sensor',
--     'sk_test_abc123def456ghi789jkl012mno345pqr678stu901vwx234yza567bcd890',
--     '客厅',
--     '监测客厅的温度和湿度变化'
-- );

-- 示例设备2: 智能开关
-- INSERT INTO devices (device_id, device_name, device_type, secret_key, location, description)
-- VALUES (
--     'dev-002-switch-power-001',
--     '卧室空调开关',
--     'switch',
--     'sk_test_bcd234efg567hij890klm123nop456qrs789tuv012wxy345zab678cde901',
--     '卧室',
--     '控制卧室空调的开关状态'
-- );

-- 示例阈值配置: 温度报警 (温度范围 18°C ~ 30°C)
-- INSERT INTO threshold_configs (device_id, metric_name, metric_unit, min_value, max_value)
-- VALUES ('dev-001-sensor-temp-hum-001', 'temperature', '°C', 18.0, 30.0);

-- 示例阈值配置: 湿度报警 (湿度范围 40% ~ 70%)
-- INSERT INTO threshold_configs (device_id, metric_name, metric_unit, min_value, max_value)
-- VALUES ('dev-001-sensor-temp-hum-001', 'humidity', '%', 40.0, 70.0);

-- -----------------------------------------------------------
-- 7. 常用查询示例 (参考)
-- -----------------------------------------------------------
-- 查询某个设备的最近状态:
--   SELECT * FROM device_status WHERE device_id = 'xxx' ORDER BY reported_at DESC LIMIT 1;

-- 查询某个设备在指定时间范围内的状态:
--   SELECT * FROM device_status
--   WHERE device_id = 'xxx' AND reported_at BETWEEN '2024-01-01' AND '2024-01-07'
--   ORDER BY reported_at DESC;

-- 查询所有未确认的报警:
--   SELECT * FROM alerts WHERE is_acknowledged = FALSE ORDER BY reported_at DESC;

-- 查询某个设备的所有报警记录:
--   SELECT * FROM alerts WHERE device_id = 'xxx' ORDER BY reported_at DESC;

-- 查询指定时间范围内的报警:
--   SELECT * FROM alerts
--   WHERE reported_at BETWEEN '2024-01-01' AND '2024-01-07'
--   ORDER BY reported_at DESC;

-- 从 JSONB 字段中提取特定指标:
--   SELECT status_data->>'temperature' AS temperature, reported_at
--   FROM device_status WHERE device_id = 'xxx' ORDER BY reported_at DESC LIMIT 10;
