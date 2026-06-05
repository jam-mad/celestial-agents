// ZodiacAgent.cs
//
// Base MonoBehaviour for all 12 zodiac agents in the Unity scene.
// Reads static traits from an assigned ZodiacData ScriptableObject and
// exposes effective (blended) values to subclasses that drive movement, glow,
// and encounter logic.
//
// Setup:
//   1. Add this component (or a subclass) to each of the 12 agent GameObjects.
//   2. Assign the matching ZodiacData asset to the SignData field.
//      The sign name is read from that asset — no separate string field needed.
//   3. Assign each agent to ZodiacWebSocketClient.Agents[] in the scene.

using UnityEngine;

public class ZodiacAgent : MonoBehaviour
{
    // -----------------------------------------------------------------------
    // Static data asset — assign in Inspector
    // -----------------------------------------------------------------------
    [Header("Sign Data")]
    [SerializeField] private ZodiacData signData;

    public string SignName => signData != null ? signData.signName : string.Empty;

    // -----------------------------------------------------------------------
    // Convenience accessors for static trait values.
    // Components outside this class (e.g. ZodiacAgentPrimitive) read through
    // these rather than touching signData directly.
    // -----------------------------------------------------------------------
    public float BaseSpeed          => signData != null ? signData.baseSpeed          : 0f;
    public float BaseGlow           => signData != null ? signData.baseGlow           : 0f;
    public float OrbitRadius        => signData != null ? signData.orbitRadius        : 1f;
    public float Restlessness       => signData != null ? signData.restlessness       : 0f;
    public float ApproachBias       => signData != null ? signData.approachBias       : 0.5f;
    public float SocialBias         => signData != null ? signData.socialBias         : 0.5f;
    public float InteractionRadius  => signData != null ? signData.interactionRadius  : 2f;
    public float HoroscopeWeight    => signData != null ? signData.horoscopeWeight    : 0.8f;
    public float StarGlow           => signData != null ? signData.starGlow           : 0.5f;

    // -----------------------------------------------------------------------
    // Daily behavior vector — applied by ZodiacWebSocketClient on receipt
    // -----------------------------------------------------------------------
    public BehaviorVectorData CurrentVector { get; private set; } = BehaviorVectorData.Neutral;

    // -----------------------------------------------------------------------
    // Effective (blended) values
    // Formula: static_baseline + (vector_modifier * horoscopeWeight)
    // The modifier is in [-1, 1], so a Fixed sign (weight=0.40) barely moves
    // from baseline while a Mutable sign (weight=1.00) swings fully.
    //
    // EffectiveGlow uses a different formula: StarGlow is the CEILING for how
    // bright this sign's star can get. GlowFloor is the minimum all agents
    // emit regardless of star or mood — no sign should be fully dark because
    // all constellation stars are visible to the naked eye.
    // At mood floor:    EffectiveGlow = GlowFloor         (always-on floor)
    // At mood ceiling:  EffectiveGlow = StarGlow           (star's max brightness)
    // -----------------------------------------------------------------------
    private const float GlowFloor = 0.08f;

    public float EffectiveSpeed     => Mathf.Clamp01(BaseSpeed         + CurrentVector.speed_mod    * HoroscopeWeight);
    public float EffectiveGlow
    {
        get
        {
            float blended = Mathf.Clamp01(BaseGlow + CurrentVector.glow_mod * HoroscopeWeight);
            return Mathf.Lerp(GlowFloor, StarGlow, blended);
        }
    }
    public float EffectiveApproach  => Mathf.Clamp01(ApproachBias      + CurrentVector.approach_mod * HoroscopeWeight);
    public float EffectiveSocial    => Mathf.Clamp01(SocialBias        + CurrentVector.social_mod   * HoroscopeWeight);
    public float EffectiveAgitation => Mathf.Clamp01(Restlessness      + CurrentVector.agitation    * HoroscopeWeight);

    // -----------------------------------------------------------------------
    // Called by ZodiacWebSocketClient when a new vector arrives
    // -----------------------------------------------------------------------
    public void ApplyBehaviorVector(BehaviorVectorData vector)
    {
        Debug.Log($"[ZodiacAgent] {SignName} ApplyBehaviorVector: emotion={vector.dominant_emotion} valence={vector.valence:+0.00}");
        CurrentVector = vector;
        OnBehaviorUpdated();
    }

    // -----------------------------------------------------------------------
    // Override in subclasses to react to new vector data.
    // CurrentVector and all Effective* properties already reflect new values
    // by the time this is called.
    // -----------------------------------------------------------------------
    protected virtual void OnBehaviorUpdated() { }

    // -----------------------------------------------------------------------
    // Startup validation — catches missing asset assignment early
    // -----------------------------------------------------------------------
    protected virtual void Awake()
    {
        if (signData == null)
            Debug.LogError($"[ZodiacAgent] {gameObject.name}: SignData is not assigned.", this);
    }

    // -----------------------------------------------------------------------
    // Debug overlay — visible in Scene view via Gizmos
    // -----------------------------------------------------------------------
    private void OnDrawGizmosSelected()
    {
        float iRadius = signData != null ? signData.interactionRadius : 2f;
        float oRadius = signData != null ? signData.orbitRadius       : 1f;

        Gizmos.color = new Color(0.8f, 0.6f, 0.2f, 0.4f);
        Gizmos.DrawWireSphere(transform.position, iRadius);

        Gizmos.color = new Color(0.2f, 0.6f, 0.9f, 0.25f);
        Gizmos.DrawWireSphere(transform.position, oRadius);
    }
}