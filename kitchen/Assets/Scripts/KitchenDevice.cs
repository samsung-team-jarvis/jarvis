using TMPro;
using UnityEngine;

// 가상 주방의 장치 하나. 보드 명령(kitchen/cmd)의 target 이름으로 찾는다 (interfaces §4, HW-16).
// 장치 오브젝트(burner_1·burner_2·fryer·hood·light 등)에 붙인다. 명령 처리는 KitchenLink가 한다.
// 같은 target을 여러 오브젝트에 붙이면 함께 켜지고 꺼진다 (예: 램프 여러 개를 모두 light로).
// 켜지면 이름표 글자가 빨갛게 바뀌고, 연결한 조명은 세기에 따라 밝아진다.
public class KitchenDevice : MonoBehaviour
{
    [Tooltip("kitchen/cmd의 target과 같은 이름 (hood·burner_1·burner_2·fryer·light·aircon·fan·music). 비우면 오브젝트 이름을 쓴다")]
    [SerializeField] string target = "";

    [Tooltip("장치 이름표 (선택). 비우면 자식에서 TextMesh Pro 글자를 찾는다")]
    [SerializeField] TMP_Text label;

    [Tooltip("켜져 있을 때 이름표 색")]
    [SerializeField] Color onColor = Color.red;

    [Tooltip("켜고 끌 조명 (선택). target이 light이고 비어 있으면 자식에서 Light를 찾는다. 장면에 둔 밝기가 세기 3이다")]
    [SerializeField] Light[] lights = new Light[0];

    [Tooltip("세기 1·2·3일 때 조명 밝기 (장면에 둔 밝기에 곱하는 값)")]
    [SerializeField] float[] lightScaleByLevel = { 0.4f, 0.7f, 1f };

    [Tooltip("켜져 있을 때만 보이는 오브젝트 (불꽃·연기 파티클 등, 선택)")]
    [SerializeField] GameObject[] showWhenOn = new GameObject[0];

    Color offColor;
    float[] fullIntensity;

    public string Target => string.IsNullOrEmpty(target) ? gameObject.name : target;
    public bool On { get; private set; }
    public int Level { get; private set; }

    void Awake()
    {
        if (label == null)
            label = GetComponentInChildren<TMP_Text>(true);
        if (label != null)
            offColor = label.color;
        // 자식 Light를 자동으로 찾는 것은 조명 장치만 — 화구·후드 프리팹 안의 조명을 모르게 끄지 않게
        if (lights.Length == 0 && Target == "light")
            lights = GetComponentsInChildren<Light>(true);
        fullIntensity = new float[lights.Length];
        for (int i = 0; i < lights.Length; i++)
            fullIntensity[i] = lights[i] != null ? lights[i].intensity : 0f;
        if (label == null && lights.Length == 0 && showWhenOn.Length == 0)
            Debug.LogWarning($"[KitchenDevice] {Target}: 켜짐을 보여 줄 이름표·조명·오브젝트가 없습니다", this);
        Show(); // 시작하면 모든 장치가 꺼져 있다 (interfaces §4.4)
    }

    // 상태를 바꾸고 화면에 반영한다. 실제로 바뀌었으면 true.
    public bool Apply(bool on, int level)
    {
        int newLevel = on ? level : 0;
        bool changed = on != On || newLevel != Level;
        On = on;
        Level = newLevel;
        Show();
        return changed;
    }

    void Show()
    {
        if (label != null)
            label.color = On ? onColor : offColor;
        float scale = On && Level >= 1 && Level <= lightScaleByLevel.Length ? lightScaleByLevel[Level - 1] : 0f;
        for (int i = 0; i < lights.Length; i++)
        {
            if (lights[i] == null)
                continue;
            lights[i].enabled = On;
            lights[i].intensity = fullIntensity[i] * scale;
        }
        foreach (GameObject item in showWhenOn)
        {
            if (item != null)
                item.SetActive(On);
        }
    }
}
