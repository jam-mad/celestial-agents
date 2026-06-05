// BehaviorVectorData.cs
//
// Serializable data class carrying the decoded behavior vector for one sign.
// Field names are snake_case to match the JSON keys sent by the Python server
// exactly -- JsonUtility requires this for deserialization to work.
//
// Emotion scores are flat float fields rather than a nested class.
// JsonUtility is unreliable with nested serializable objects -- it silently
// corrupts subsequent fields when nested parsing fails. Flat floats are
// proven safe because they are the same type as the behavior modifiers that
// already deserialize correctly (speed_mod, agitation, etc).
//
// All float fields except agitation and aggression are in [-1, 1].
// agitation and aggression are in [0, 1].
// Emotion scores are in [0, 1] and sum to ~1.0.

using System;

[Serializable]
public class BehaviorVectorData
{
    // Per-emotion probability scores -- flat fields, prefixed to avoid
    // any name collision with the behavior modifier fields below.
    public float emotion_anger;
    public float emotion_disgust;
    public float emotion_fear;
    public float emotion_joy;
    public float emotion_neutral;
    public float emotion_sadness;
    public float emotion_surprise;

    // Behavior modifiers -- blended with static traits via horoscopeWeight.
    public float speed_mod;       // [-1, 1]
    public float agitation;       // [ 0, 1]
    public float approach_mod;    // [-1, 1]
    public float glow_mod;        // [-1, 1]
    public float social_mod;      // [-1, 1]
    public float aggression;      // [ 0, 1]
    public float valence;         // [-1, 1]

    // Metadata
    public string dominant_emotion;

    public static BehaviorVectorData Neutral => new BehaviorVectorData
    {
        emotion_neutral  = 1f,
        dominant_emotion = "neutral",
    };
}