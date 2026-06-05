// ZodiacMessages.cs
//
// Serializable message wrapper classes for JsonUtility deserialization.
// Each class maps directly to one inbound WebSocket message type from
// the Python server. Field names must match JSON keys exactly.
//
// These are internal to the WebSocket layer — nothing outside
// ZodiacWebSocketClient should reference them directly.

using System;
using UnityEngine;

// First-pass parse — reads only the "type" field to route the message.
[Serializable]
internal class ZodiacMessageType
{
    public string type;
}

// "daily_update" — sent on connect and in response to request_date.
[Serializable]
internal class DailyUpdateMessage
{
    public string       type;
    public string       date;
    public VectorEntry[] vectors;
}

// One entry in the daily_update vectors array.
[Serializable]
internal class VectorEntry
{
    public string           sign;
    public BehaviorVectorData vector;
}

// "sign_update" — sent in response to request_sign or an override push.
[Serializable]
internal class SignUpdateMessage
{
    public string           type;
    public string           sign;
    public string           date;
    public BehaviorVectorData vector;
}