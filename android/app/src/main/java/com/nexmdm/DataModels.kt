package com.nexmdm

import com.google.gson.annotations.SerializedName

data class HeartbeatPayload(
    @SerializedName("device_id") val device_id: String,
    @SerializedName("alias") val alias: String,
    @SerializedName("app_version") val app_version: String,
    @SerializedName("timestamp_utc") val timestamp_utc: String,
    @SerializedName("app_versions") val app_versions: Map<String, AppVersion>,
    @SerializedName("speedtest_running_signals") val speedtest_running_signals: SpeedtestRunningSignals,
    @SerializedName("battery") val battery: Map<String, Any?>,
    @SerializedName("system") val system: Map<String, Any?>,
    @SerializedName("memory") val memory: Map<String, Any?>,
    @SerializedName("network") val network: Map<String, Any?>,
    @SerializedName("fcm_token") val fcm_token: String?,
    @SerializedName("is_ping_response") val is_ping_response: Boolean?,
    @SerializedName("ping_request_id") val ping_request_id: String?,
    @SerializedName("self_heal_hints") val self_heal_hints: List<String>?,
    @SerializedName("is_device_owner") val is_device_owner: Boolean?,
    @SerializedName("power_ok") val power_ok: Boolean?,
    @SerializedName("doze_whitelisted") val doze_whitelisted: Boolean?,
    @SerializedName("net_validated") val net_validated: Boolean?,
    @SerializedName("queue_depth") val queue_depth: Int?,
    @SerializedName("monitored_foreground_recent_s") val monitored_foreground_recent_s: Int?,
    @SerializedName("unity_process_running") val unity_process_running: Boolean?
)

data class AppVersion(
    @SerializedName("installed") val installed: Boolean,
    @SerializedName("version_name") val version_name: String?,
    @SerializedName("version_code") val version_code: Long?
)

data class SpeedtestRunningSignals(
    @SerializedName("has_service_notification") val has_service_notification: Boolean,
    @SerializedName("foreground_recent_seconds") val foreground_recent_seconds: Int
)
