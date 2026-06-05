// ZodiacWebSocketClient.cs
//
// Manages the WebSocket connection to the Python behavior server.
// Uses Unity's built-in System.Net.WebSockets and JsonUtility —
// no external packages required beyond com.unity.nuget.newtonsoft-json
// (which is no longer needed and can be removed from the project).
//
// Setup:
//   1. Add this component to a single manager GameObject (e.g. "ZodiacManager").
//   2. Drag all 12 ZodiacAgent GameObjects into the Agents array in the Inspector.
//   3. Make sure the Python server is running before entering Play mode.

using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using UnityEngine;

public class ZodiacWebSocketClient : MonoBehaviour
{
    // -----------------------------------------------------------------------
    // Inspector fields
    // -----------------------------------------------------------------------
    [Header("Connection")]
    [SerializeField] private string serverUrl  = "ws://localhost:8765";
    [SerializeField] private float  retryDelay = 5f;

    [Header("Agents")]
    [SerializeField] private ZodiacAgent[] agents;

    // -----------------------------------------------------------------------
    // Internal state
    // -----------------------------------------------------------------------
    private ClientWebSocket                  _socket;
    private CancellationTokenSource         _cts;
    private Dictionary<string, ZodiacAgent> _agentBySign;

    // Messages arrive on a background thread; queue them for main-thread dispatch.
    private readonly ConcurrentQueue<string> _messageQueue = new ConcurrentQueue<string>();

    private const int ReceiveBufferSize = 8192;

    // -----------------------------------------------------------------------
    // Unity lifecycle
    // -----------------------------------------------------------------------
    private void Start()
    {
        BuildLookup();
        _cts = new CancellationTokenSource();
        _ = ConnectLoop(_cts.Token);
    }

    private void Update()
    {
        // Drain the queue on the main thread so Unity API calls are safe.
        while (_messageQueue.TryDequeue(out var raw))
            HandleMessage(raw);
    }

    private void OnDestroy()
    {
        _cts?.Cancel();
        _socket?.Dispose();
    }

    // -----------------------------------------------------------------------
    // Connection management
    // -----------------------------------------------------------------------
    private void BuildLookup()
    {
        _agentBySign = new Dictionary<string, ZodiacAgent>(StringComparer.OrdinalIgnoreCase);
        foreach (var agent in agents)
        {
            if (agent == null) continue;
            _agentBySign[agent.SignName] = agent;
        }
        Debug.Log($"[ZodiacWS] Registered {_agentBySign.Count} agents.");
    }

    private async Task ConnectLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            _socket?.Dispose();
            _socket = new ClientWebSocket();

            try
            {
                Debug.Log($"[ZodiacWS] Connecting to {serverUrl} …");
                await _socket.ConnectAsync(new Uri(serverUrl), ct);
                Debug.Log("[ZodiacWS] Connected.");
                await ReceiveLoop(ct);
            }
            catch (OperationCanceledException) { break; }
            catch (Exception e)
            {
                Debug.LogWarning($"[ZodiacWS] Connection lost: {e.Message}. Retrying in {retryDelay}s …");
            }

            try { await Task.Delay(TimeSpan.FromSeconds(retryDelay), ct); }
            catch (OperationCanceledException) { break; }
        }

        Debug.Log("[ZodiacWS] Connect loop exited.");
    }

    private async Task ReceiveLoop(CancellationToken ct)
    {
        var buffer = new byte[ReceiveBufferSize];
        var sb     = new StringBuilder();

        while (_socket.State == WebSocketState.Open && !ct.IsCancellationRequested)
        {
            WebSocketReceiveResult result;
            try
            {
                result = await _socket.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
            }
            catch (OperationCanceledException) { break; }
            catch (WebSocketException e)
            {
                Debug.LogWarning($"[ZodiacWS] Receive error: {e.Message}");
                break;
            }

            if (result.MessageType == WebSocketMessageType.Close)
            {
                Debug.Log("[ZodiacWS] Server closed connection.");
                break;
            }

            sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));

            if (result.EndOfMessage)
            {
                _messageQueue.Enqueue(sb.ToString());
                sb.Clear();
            }
        }
    }

    // -----------------------------------------------------------------------
    // Inbound message routing (runs on main thread via Update)
    // -----------------------------------------------------------------------
    private void HandleMessage(string raw)
    {
        // First pass: read only the type field to route without full parse.
        var envelope = JsonUtility.FromJson<ZodiacMessageType>(raw);
        if (envelope == null) return;

        switch (envelope.type)
        {
            case "daily_update": HandleDailyUpdate(raw); break;
            case "sign_update":  HandleSignUpdate(raw);  break;
            default:
                Debug.LogWarning($"[ZodiacWS] Unknown message type: {envelope.type}");
                break;
        }
    }

    private void HandleDailyUpdate(string raw)
    {
        var msg = JsonUtility.FromJson<DailyUpdateMessage>(raw);
        if (msg?.vectors == null) { Debug.LogWarning("[ZodiacWS] daily_update: vectors null after parse"); return; }

        Debug.Log($"[ZodiacWS] Parsed {msg.vectors.Length} entries. First: sign={msg.vectors[0].sign} emotion={msg.vectors[0].vector?.dominant_emotion}");

        foreach (var entry in msg.vectors)
            ApplyToAgent(entry.sign, entry.vector);
    }

    private void HandleSignUpdate(string raw)
    {
        var msg = JsonUtility.FromJson<SignUpdateMessage>(raw);
        if (msg == null) return;
        ApplyToAgent(msg.sign, msg.vector);
    }

    private void ApplyToAgent(string sign, BehaviorVectorData data)
    {
        if (sign == null) return;
        if (!_agentBySign.TryGetValue(sign, out var agent))
        {
            Debug.LogWarning($"[ZodiacWS] No agent registered for '{sign}'.");
            return;
        }

        agent.ApplyBehaviorVector(data);
        Debug.Log($"[ZodiacWS] {sign}: {data.dominant_emotion}  valence={data.valence:+0.00}");
    }

    // -----------------------------------------------------------------------
    // Outbound requests — called by Gradio bridge or in-scene UI
    // -----------------------------------------------------------------------

    /// <summary>Request a fresh vector for one sign, optionally on a specific date.</summary>
    public void RequestSign(string signName, DateTime? forDate = null)
    {
        var d   = (forDate ?? DateTime.Today).ToString("yyyy-MM-dd");
        var msg = $"{{\"type\":\"request_sign\",\"sign\":\"{signName.ToLower()}\",\"date\":\"{d}\"}}";
        _ = SendAsync(msg);
    }

    /// <summary>Request all 12 vectors for a specific calendar date.</summary>
    public void RequestDate(DateTime forDate)
    {
        var d   = forDate.ToString("yyyy-MM-dd");
        var msg = $"{{\"type\":\"request_date\",\"date\":\"{d}\"}}";
        _ = SendAsync(msg);
    }

    private async Task SendAsync(string text)
    {
        if (_socket?.State != WebSocketState.Open) return;
        var bytes = Encoding.UTF8.GetBytes(text);
        try
        {
            await _socket.SendAsync(
                new ArraySegment<byte>(bytes),
                WebSocketMessageType.Text,
                endOfMessage: true,
                _cts.Token
            );
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[ZodiacWS] Send failed: {e.Message}");
        }
    }
}