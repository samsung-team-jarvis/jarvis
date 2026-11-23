using TMPro;
using UnityEngine;

// 가상 주방의 장치 하나. 보드 명령(kitchen/cmd)의 target 이름으로 찾는다 (interfaces §4, HW-16).
// 장치 오브젝트(burner_1·burner_2·fryer·hood 등)에 붙인다. 명령 처리는 KitchenLink가 한다.
// 켜지면 장치의 이름표 글자가 빨갛게 바뀐다.
public class KitchenDevice : MonoBehaviour
{
    [Tooltip("kitchen/cmd의 target과 같은 이름. 비우면 오브젝트 이름을 쓴다")]
    [SerializeField] string target = "";

    [Tooltip("장치 이름표. 비우면 자식에서 TextMesh Pro 글자를 찾는다")]
    [SerializeField] TMP_Text label;

    [Tooltip("켜져 있을 때 이름표 색")]
    [SerializeField] Color onColor = Color.red;

    [Tooltip("켜져 있을 때만 보이는 오브젝트 (불꽃·연기 파티클 등, 선택)")]
    [SerializeField] GameObject[] showWhenOn = new GameObject[0];

    Color offColor;

    public string Target => string.IsNullOrEmpty(target) ? gameObject.name : target;
    public bool On { get; private set; }
    public int Level { get; private set; }

    void Awake()
    {
        if (label == null)
            label = GetComponentInChildren<TMP_Text>(true);
        if (label != null)
            offColor = label.color;
        else
            Debug.LogWarning($"[KitchenDevice] {Target}: 이름표(TextMesh Pro)를 찾지 못했습니다", this);
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
        foreach (GameObject item in showWhenOn)
        {
            if (item != null)
                item.SetActive(On);
        }
    }
}
