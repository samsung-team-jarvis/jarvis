using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Protocol;
using UnityEngine;

// 보드의 MQTT 브로커에 접속해 장치 명령(kitchen/cmd)을 받아 실행하고 확인(kitchen/ack)을 보낸다 (HW-16).
// 규격: docs/architecture/interfaces.md §4, recipes/unity-kitchen-link.md.
// 같은 동작의 Python 구현: services/kitchen_gw/fake_kitchen.py.
// 장면에 빈 오브젝트 하나를 만들어 붙이고, Broker Host에 보드 IP를 넣는다.
public class KitchenLink : MonoBehaviour
{
    const string TopicCmd = "kitchen/cmd";
    const string TopicAck = "kitchen/ack";
    const string TopicState = "kitchen/state";
    const int RememberedSeqs = 64; // 재전송 중복을 막으려고 기억하는 최근 seq 수
    const int ReconnectDelayMs = 2000;

    // common/function_call.py의 DEVICES (interfaces §2.2)
    static readonly HashSet<string> KnownDevices = new HashSet<string>
    {
        "hood", "burner_1", "burner_2", "fryer", "light", "aircon", "fan", "music",
    };

    [Tooltip("보드 IP (보드 없이 시험할 때는 127.0.0.1)")]
    [SerializeField] string brokerHost = "127.0.0.1";
    [SerializeField] int brokerPort = 1883;
    [Tooltip("주고받는 메시지를 Console에 출력")]
    [SerializeField] bool logMessages = true;

    [Serializable]
    class Command
    {
        public int seq;
        public string cmd;
        public string target;
        public int value;
    }

    IMqttClient client;
    CancellationTokenSource cancel;
    volatile bool justConnected;

    // MQTT 메시지는 Unity 메인 스레드가 아닌 곳에서 도착한다. 여기에 넣어 두고 Update에서 꺼내 처리한다.
    readonly ConcurrentQueue<string> inbox = new ConcurrentQueue<string>();
    readonly Dictionary<int, string> acks = new Dictionary<int, string>();
    readonly Queue<int> ackOrder = new Queue<int>();
    // target 이름 → 그 이름을 가진 오브젝트들. 같은 target이 여러 개면 함께 켜고 끈다 (예: 램프 여러 개 = light)
    readonly Dictionary<string, List<KitchenDevice>> devices = new Dictionary<string, List<KitchenDevice>>();

    public bool Connected => client != null && client.IsConnected;

    void Awake()
    {
        // 에디터 창이 포커스를 잃어도 Update가 돌아야 확인이 늦지 않는다 (보드는 0.5초 안에 ack를 기다린다).
        Application.runInBackground = true;
        foreach (KitchenDevice device in FindObjectsByType<KitchenDevice>(FindObjectsSortMode.None))
        {
            if (!devices.TryGetValue(device.Target, out List<KitchenDevice> group))
                devices[device.Target] = group = new List<KitchenDevice>();
            group.Add(device);
            if (!KnownDevices.Contains(device.Target))
                Debug.LogWarning($"[KitchenLink] 규격에 없는 이름이라 보드가 제어할 수 없습니다: {device.Target}", device);
        }
        var names = new List<string>();
        foreach (KeyValuePair<string, List<KitchenDevice>> pair in devices)
            names.Add(pair.Value.Count > 1 ? $"{pair.Key}×{pair.Value.Count}" : pair.Key);
        Debug.Log($"[KitchenLink] 장치 {devices.Count}개: {string.Join(", ", names)}");
    }

    void OnEnable()
    {
        cancel = new CancellationTokenSource();
        _ = RunAsync(cancel.Token);
    }

    void OnDisable()
    {
        cancel?.Cancel();
        IMqttClient old = client;
        client = null;
        if (old != null)
            _ = old.DisconnectAsync().ContinueWith(_ => old.Dispose());
    }

    // 연결이 끊기면 2초마다 다시 접속한다.
    async Task RunAsync(CancellationToken token)
    {
        IMqttClient mqtt = new MqttFactory().CreateMqttClient();
        client = mqtt;
        mqtt.ApplicationMessageReceivedAsync += e =>
        {
            ArraySegment<byte> payload = e.ApplicationMessage.PayloadSegment;
            inbox.Enqueue(Encoding.UTF8.GetString(payload.Array, payload.Offset, payload.Count));
            return Task.CompletedTask;
        };
        string clientId = "kitchen_unity_" + Guid.NewGuid().ToString("N").Substring(0, 8);
        MqttClientSubscribeOptions subscribe = new MqttFactory().CreateSubscribeOptionsBuilder()
            .WithTopicFilter(TopicCmd, MqttQualityOfServiceLevel.AtMostOnce)
            .Build();

        while (!token.IsCancellationRequested)
        {
            if (!mqtt.IsConnected)
            {
                // 접속할 때마다 주소를 다시 읽는다 — Play 중에 Inspector에서 바꿔도 다음 시도에 반영된다
                string host = brokerHost.Trim();
                int port = brokerPort;
                MqttClientOptions options = new MqttClientOptionsBuilder()
                    .WithTcpServer(host, port)
                    .WithClientId(clientId)
                    .WithCleanSession()
                    .WithTimeout(TimeSpan.FromSeconds(3))
                    .Build();
                try
                {
                    await mqtt.ConnectAsync(options, token);
                    await mqtt.SubscribeAsync(subscribe, token);
                    Debug.Log($"[KitchenLink] 접속: {host}:{port}, {TopicCmd} 구독");
                    justConnected = true;
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[KitchenLink] 접속 실패 {host}:{port} — {ex.Message}");
                }
            }
            try
            {
                await Task.Delay(ReconnectDelayMs, token);
            }
            catch (OperationCanceledException)
            {
                break;
            }
        }
    }

    void Update()
    {
        if (justConnected)
        {
            justConnected = false;
            PublishState(); // 접속하면 지금 상태를 한 번 알린다
        }
        while (inbox.TryDequeue(out string json))
            Handle(json);
    }

    void Handle(string json)
    {
        if (logMessages)
            Debug.Log($"[{TopicCmd}] {json}");
        Command command;
        try
        {
            command = JsonUtility.FromJson<Command>(json);
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"[KitchenLink] 명령을 읽지 못했습니다: {ex.Message}");
            return;
        }
        if (command == null || !json.Contains("\"seq\""))
            return; // seq가 없으면 누구에게 답할지 모른다

        // 이미 처리한 seq: 장치는 그대로 두고 확인만 다시 보낸다 (보드의 재전송, interfaces §4.3)
        if (acks.TryGetValue(command.seq, out string previous))
        {
            Publish(TopicAck, previous);
            return;
        }
        string ack = Execute(command, out bool changed);
        Remember(command.seq, ack);
        if (changed)
            PublishState();
        Publish(TopicAck, ack); // 장치를 바꾼 뒤에 보낸다
    }

    string Execute(Command c, out bool changed)
    {
        changed = false;
        if (!IsValid(c))
            return Ack(c.seq, false, "invalid_command");
        if (c.cmd == "OFF" && c.target == "all")
        {
            foreach (List<KitchenDevice> all in devices.Values)
                foreach (KitchenDevice device in all)
                    changed |= device.Apply(false, 0);
            return Ack(c.seq, true, null);
        }
        if (!devices.TryGetValue(c.target, out List<KitchenDevice> group))
            return Ack(c.seq, false, "unknown_target"); // 규격엔 있지만 아직 장면에 없는 장치
        // ON은 세기 1, LEVEL은 꺼져 있으면 켜면서 세기를 맞춘다
        foreach (KitchenDevice device in group)
            changed |= c.cmd == "OFF" ? device.Apply(false, 0) : device.Apply(true, c.value);
        return Ack(c.seq, true, null);
    }

    // common/kitchen_link.py의 validate_command와 같은 규칙
    static bool IsValid(Command c)
    {
        if (c.seq < 0)
            return false;
        bool knownTarget = c.target != null && KnownDevices.Contains(c.target);
        switch (c.cmd)
        {
            case "ON":
                return knownTarget && c.value == 1;
            case "OFF":
                return (knownTarget || c.target == "all") && c.value == 0;
            case "LEVEL":
                return knownTarget && c.value >= 1 && c.value <= 3;
            default:
                return false;
        }
    }

    static string Ack(int seq, bool ok, string reason)
    {
        if (ok)
            return $"{{\"seq\":{seq},\"ok\":true}}";
        return $"{{\"seq\":{seq},\"ok\":false,\"reason\":\"{reason}\"}}";
    }

    void Remember(int seq, string ack)
    {
        acks[seq] = ack;
        ackOrder.Enqueue(seq);
        while (ackOrder.Count > RememberedSeqs)
            acks.Remove(ackOrder.Dequeue());
    }

    // kitchen/state: {"devices": {"hood": {"on": true, "level": 1}, ...}, "safe_stop": false}
    // 지금은 상태가 바뀔 때만 보낸다. 5초 주기 보고와 safe_stop은 HW-18에서 붙인다.
    void PublishState()
    {
        var parts = new List<string>();
        foreach (KeyValuePair<string, List<KitchenDevice>> pair in devices)
        {
            KitchenDevice d = pair.Value[0]; // 같은 target끼리는 늘 같은 상태다
            parts.Add($"\"{pair.Key}\":{{\"on\":{(d.On ? "true" : "false")},\"level\":{d.Level}}}");
        }
        Publish(TopicState, $"{{\"devices\":{{{string.Join(",", parts)}}},\"safe_stop\":false}}");
    }

    void Publish(string topic, string json)
    {
        IMqttClient mqtt = client;
        if (mqtt == null || !mqtt.IsConnected)
        {
            Debug.LogWarning($"[KitchenLink] 접속 전이라 보내지 못했습니다: {topic} {json}");
            return;
        }
        if (logMessages)
            Debug.Log($"[{topic}] {json}");
        MqttApplicationMessage message = new MqttApplicationMessageBuilder()
            .WithTopic(topic)
            .WithPayload(Encoding.UTF8.GetBytes(json))
            .WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtMostOnce)
            .Build();
        _ = PublishAsync(mqtt, message);
    }

    async Task PublishAsync(IMqttClient mqtt, MqttApplicationMessage message)
    {
        try
        {
            await mqtt.PublishAsync(message, cancel.Token);
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"[KitchenLink] 보내기 실패 {message.Topic}: {ex.Message}");
        }
    }
}
