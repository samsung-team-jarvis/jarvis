using UnityEngine;

public class FaceCamera : MonoBehaviour
{
    [SerializeField] private Camera targetCamera;

    private void LateUpdate()
    {
        if (targetCamera != null)
            transform.rotation = targetCamera.transform.rotation;
    }
}
