// ZodiacAgentPrimitive.cs
//
// v1 visual driver for a primitive-shape zodiac agent.
// Reads Effective* properties from ZodiacAgent to drive:
//   - wandering movement around a home anchor
//   - self-rotation
//   - emissive glow (emission layer only -- never touches base color)
//   - a child Point Light for inter-agent light bleed
//   - social drift toward or away from nearby agents
//
// Material behavior:
//   The script only writes _EmissionColor. It never touches _BaseColor or _Color,
//   so whatever color you set on the material in the Inspector is preserved.
//   On Awake, the script checks whether the material shader supports emission.
//   If it doesn't, a one-time warning is logged and the glow path is disabled --
//   movement and social logic still run normally.
//
// Lighting:
//   A Point Light is created as a child of each agent at runtime. Its range
//   matches InteractionRadius and its intensity tracks EffectiveGlow, so nearby
//   agents' surfaces are actually lit by each other. Pair with Bloom in a URP
//   Global Volume for the full effect: Bloom handles the orb glow, the Point
//   Light handles the inter-agent light bleed.
//
// Setup:
//   1. Attach to each agent GameObject (replaces bare ZodiacAgent).
//   2. Assign the matching ZodiacData asset to the SignData field.
//   3. Space the 12 agents in the scene -- a ring works well.
//   4. Add a URP Global Volume with Bloom enabled (threshold ~0.9) for
//      perceptible glow pulsing. The Point Lights work without it.

using System.Collections.Generic;
using UnityEngine;

[RequireComponent(typeof(Renderer))]
public class ZodiacAgentPrimitive : ZodiacAgent
{
    [Header("Movement")]
    [SerializeField] private float baseMoveSpeed    = 2.0f;
    [SerializeField] private float retargetInterval = 2.0f;
    [SerializeField] private float rotationSpeed    = 30.0f;

    [Header("Glow")]
    [SerializeField] private float glowPulseSpeed      = 1.5f;
    [SerializeField] private float maxEmission         = 2.5f;   // HDR ceiling, feeds Bloom
    [SerializeField] private float colorToggleInterval = 3.0f;   // seconds between material/emotion color swap

    [Header("Point Light")]
    [SerializeField] private float maxLightIntensity = 3.0f;
    [SerializeField] private float lightRangeScale   = 1.2f; // multiplier on InteractionRadius

    [Header("Social")]
    [SerializeField] private float socialDriftStrength = 0.5f;

    private Vector3 _anchor;
    private Vector3 _wanderTarget;
    private float   _retargetTimer;
    private float   _pulsePhase;
    private float   _colorToggleTimer;

    private Renderer _renderer;
    private Material _mat;
    private bool     _emissionSupported;
    private Light    _pointLight;
    private Color    _targetEmotionColor = new Color(0.70f, 0.70f, 0.70f);

    private static readonly List<ZodiacAgentPrimitive> _all = new();

    // -----------------------------------------------------------------------
    // Lifecycle
    // -----------------------------------------------------------------------
    protected override void Awake()
    {
        base.Awake();

        _anchor   = transform.position;
        _renderer = GetComponent<Renderer>();

        // renderer.material auto-creates a per-instance copy so we never
        // modify the shared asset. We own this instance and destroy it OnDestroy.
        _mat = _renderer.material;

        _emissionSupported = _mat.HasProperty("_EmissionColor");
        if (_emissionSupported)
        {
            _mat.EnableKeyword("_EMISSION");
        }
        else
        {
            Debug.LogWarning(
                $"[ZodiacAgentPrimitive] {gameObject.name}: material '{_mat.name}' " +
                "does not support _EmissionColor. Glow disabled for this agent. " +
                "Use a URP Lit or Unlit shader with emission enabled.",
                this
            );
        }

        _pulsePhase = Random.value * Mathf.PI * 2f;
        PickNewWanderTarget();
        CreatePointLight();
    }

    private void CreatePointLight()
    {
        var child = new GameObject("AgentLight");
        child.transform.SetParent(transform, false);
        child.transform.localPosition = Vector3.zero;

        _pointLight           = child.AddComponent<Light>();
        _pointLight.type      = LightType.Point;
        _pointLight.range     = InteractionRadius * lightRangeScale;
        _pointLight.intensity = 0f;
        _pointLight.shadows   = LightShadows.None;
    }

    private void OnEnable()  => _all.Add(this);
    private void OnDisable() => _all.Remove(this);

    private void OnDestroy()
    {
        if (_mat != null) Destroy(_mat);
    }

    private void Update()
    {
        UpdateMovement();
        UpdateRotation();
        UpdateGlow();
    }

    // -----------------------------------------------------------------------
    // Movement
    // -----------------------------------------------------------------------
    private void UpdateMovement()
    {
        float agitation = EffectiveAgitation;
        float interval  = Mathf.Lerp(retargetInterval, retargetInterval * 0.2f, agitation);

        _retargetTimer -= Time.deltaTime;
        if (_retargetTimer <= 0f || Vector3.Distance(transform.position, _wanderTarget) < 0.3f)
        {
            PickNewWanderTarget();
            _retargetTimer = interval;
        }

        Vector3 desired = _wanderTarget + ComputeSocialDrift();
        float   speed   = baseMoveSpeed * Mathf.Max(EffectiveSpeed, 0.05f);

        if (agitation > 0.01f)
        {
            float   t      = Time.time * 5f;
            Vector3 jitter = new Vector3(
                Mathf.PerlinNoise(t,          _pulsePhase)   - 0.5f,
                Mathf.PerlinNoise(_pulsePhase, t)            - 0.5f,
                Mathf.PerlinNoise(t + 13.7f,  t + 13.7f)    - 0.5f
            ) * (agitation * 0.5f);
            desired += jitter;
        }

        transform.position = Vector3.MoveTowards(transform.position, desired, speed * Time.deltaTime);
    }

    private void PickNewWanderTarget()
    {
        _wanderTarget = _anchor + Random.insideUnitSphere * OrbitRadius;
    }

    private Vector3 ComputeSocialDrift()
    {
        float   bias  = EffectiveSocial;
        float   sign  = (bias - 0.5f) * 2f;
        Vector3 drift = Vector3.zero;
        int     count = 0;

        foreach (var other in _all)
        {
            if (other == this) continue;
            Vector3 to   = other.transform.position - transform.position;
            float   dist = to.magnitude;
            if (dist < InteractionRadius && dist > 0.01f)
            {
                drift += (to / dist) * sign;
                count++;
            }
        }

        if (count > 0)
            drift = (drift / count) * socialDriftStrength * OrbitRadius;

        return drift;
    }

    // -----------------------------------------------------------------------
    // Rotation
    // -----------------------------------------------------------------------
    private void UpdateRotation()
    {
        float rate   = rotationSpeed * Mathf.Max(EffectiveSpeed, 0.05f);
        float wobble = EffectiveAgitation * 30f * Mathf.Sin(Time.time * 10f);
        transform.Rotate(Vector3.up, (rate + wobble) * Time.deltaTime, Space.World);
    }

    // -----------------------------------------------------------------------
    // React to a new behavior vector
    // -----------------------------------------------------------------------
    protected override void OnBehaviorUpdated()
    {
        // Reset to colorToggleInterval (not 0) so the cycle starts at the
        // emotion color phase -- new emotion is immediately visible rather
        // than taking 3 seconds to fade in from material color.
        _colorToggleTimer = colorToggleInterval;

        // Cache now while CurrentVector is guaranteed to reflect the new data.
        // UpdateGlow runs later each frame and uses this cached value so a
        // subsequent ApplyBehaviorVector call cannot overwrite it mid-frame.
        _targetEmotionColor = ComputeEmotionColor();

        Debug.Log(
            $"[{SignName}] vector updated — " +
            $"dominant: {CurrentVector.dominant_emotion}  valence: {CurrentVector.valence:+0.00}\n" +
            $"  joy={CurrentVector.emotion_joy:F3}  fear={CurrentVector.emotion_fear:F3}  " +
            $"anger={CurrentVector.emotion_anger:F3}  sadness={CurrentVector.emotion_sadness:F3}  " +
            $"surprise={CurrentVector.emotion_surprise:F3}  neutral={CurrentVector.emotion_neutral:F3}\n" +
            $"  => emotion color #{ColorUtility.ToHtmlStringRGB(_targetEmotionColor)}"
        );
    }

    // -----------------------------------------------------------------------
    // Glow and Point Light
    // -----------------------------------------------------------------------
    private void UpdateGlow()
    {
        float pulseSpeed = glowPulseSpeed * (1f + EffectiveAgitation * 2f);
        _pulsePhase += Time.deltaTime * pulseSpeed;
        float pulse     = 0.75f + 0.25f * Mathf.Sin(_pulsePhase);
        float glowValue = EffectiveGlow * pulse;

        _colorToggleTimer += Time.deltaTime;
        float t     = (_colorToggleTimer % (colorToggleInterval * 2f)) / (colorToggleInterval * 2f);
        float blend = 0.5f - 0.5f * Mathf.Cos(t * Mathf.PI * 2f);

        Color matColor = _mat.HasProperty("_BaseColor")
            ? _mat.GetColor("_BaseColor")
            : _mat.HasProperty("_Color")
                ? _mat.GetColor("_Color")
                : Color.white;

        Color glowColor = Color.Lerp(matColor, _targetEmotionColor, blend);

        if (_emissionSupported)
            _mat.SetColor("_EmissionColor", glowColor * (glowValue * maxEmission));

        if (_pointLight != null)
        {
            _pointLight.color     = glowColor;
            _pointLight.intensity = glowValue * maxLightIntensity;
            _pointLight.range     = InteractionRadius * lightRangeScale;
        }
    }

    // Weighted blend of emotion colors from flat probability scores.
    // Called once per vector update and cached -- never called per-frame.
    // Scores sum to ~1.0 so the result is a normalized color.
    private Color ComputeEmotionColor()
    {
        return new Color(1.00f, 0.85f, 0.20f) * CurrentVector.emotion_joy
             + new Color(0.90f, 0.15f, 0.10f) * CurrentVector.emotion_anger
             + new Color(0.55f, 0.20f, 0.80f) * CurrentVector.emotion_fear
             + new Color(0.20f, 0.40f, 0.90f) * CurrentVector.emotion_sadness
             + new Color(1.00f, 0.50f, 0.10f) * CurrentVector.emotion_surprise
             + new Color(0.30f, 0.70f, 0.25f) * CurrentVector.emotion_disgust
             + new Color(0.70f, 0.70f, 0.70f) * CurrentVector.emotion_neutral;
    }

}