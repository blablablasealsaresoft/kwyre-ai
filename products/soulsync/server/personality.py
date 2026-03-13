"""
PersonalityEngine — Big Five, attachment style, love language, and values extraction
from questionnaire responses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AttachmentStyle(str, Enum):
    SECURE = "secure"
    ANXIOUS = "anxious"
    AVOIDANT = "avoidant"
    DISORGANIZED = "disorganized"


class LoveLanguage(str, Enum):
    WORDS = "words_of_affirmation"
    ACTS = "acts_of_service"
    GIFTS = "receiving_gifts"
    TIME = "quality_time"
    TOUCH = "physical_touch"


# Question keys mapped to Big Five dimensions with polarity (+1 or -1)
BIG_FIVE_MAP: dict[str, list[tuple[str, int]]] = {
    "openness": [
        ("enjoy_new_experiences", 1),
        ("prefer_routine", -1),
        ("appreciate_art", 1),
        ("curious_about_ideas", 1),
        ("prefer_practical", -1),
        ("enjoy_abstract_thinking", 1),
    ],
    "conscientiousness": [
        ("organized_planner", 1),
        ("finish_what_i_start", 1),
        ("spontaneous_over_planned", -1),
        ("detail_oriented", 1),
        ("procrastinate_often", -1),
        ("reliable_dependable", 1),
    ],
    "extraversion": [
        ("energized_by_people", 1),
        ("prefer_small_groups", -1),
        ("enjoy_being_center_attention", 1),
        ("need_alone_time", -1),
        ("talkative_in_groups", 1),
        ("prefer_deep_one_on_one", -1),
    ],
    "agreeableness": [
        ("trust_people_easily", 1),
        ("avoid_conflict", 1),
        ("competitive_nature", -1),
        ("empathize_with_others", 1),
        ("speak_mind_directly", -1),
        ("prioritize_harmony", 1),
    ],
    "neuroticism": [
        ("worry_frequently", 1),
        ("emotionally_stable", -1),
        ("stress_easily", 1),
        ("bounce_back_quickly", -1),
        ("overthink_decisions", 1),
        ("calm_under_pressure", -1),
    ],
}

ATTACHMENT_QUESTIONS: dict[str, list[tuple[str, int]]] = {
    "anxiety": [
        ("fear_abandonment", 1),
        ("need_constant_reassurance", 1),
        ("worry_partner_will_leave", 1),
        ("jealous_easily", 1),
        ("feel_secure_in_relationships", -1),
    ],
    "avoidance": [
        ("uncomfortable_with_closeness", 1),
        ("value_independence_highly", 1),
        ("difficulty_opening_up", 1),
        ("prefer_self_reliance", 1),
        ("enjoy_emotional_intimacy", -1),
    ],
}

LOVE_LANGUAGE_QUESTIONS: dict[LoveLanguage, list[str]] = {
    LoveLanguage.WORDS: ["value_verbal_praise", "compliments_matter", "love_hearing_i_love_you"],
    LoveLanguage.ACTS: ["actions_speak_louder", "appreciate_help_with_tasks", "thoughtful_gestures_matter"],
    LoveLanguage.GIFTS: ["love_surprise_gifts", "meaningful_presents", "gift_giving_important"],
    LoveLanguage.TIME: ["undivided_attention_matters", "quality_time_over_gifts", "shared_activities_bond"],
    LoveLanguage.TOUCH: ["physical_affection_important", "holding_hands_matters", "hugs_make_day_better"],
}

VALUES_KEYS = [
    "career_ambition", "family_priority", "adventure_seeking",
    "stability_preference", "personal_growth", "spirituality",
    "financial_security", "social_justice", "creativity_expression",
    "health_fitness", "community_belonging", "independence",
]


@dataclass
class BigFiveScores:
    openness: float = 0.0
    conscientiousness: float = 0.0
    extraversion: float = 0.0
    agreeableness: float = 0.0
    neuroticism: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "openness": round(self.openness, 2),
            "conscientiousness": round(self.conscientiousness, 2),
            "extraversion": round(self.extraversion, 2),
            "agreeableness": round(self.agreeableness, 2),
            "neuroticism": round(self.neuroticism, 2),
        }


@dataclass
class PersonalityProfile:
    user_id: str
    big_five: BigFiveScores = field(default_factory=BigFiveScores)
    attachment_style: AttachmentStyle = AttachmentStyle.SECURE
    attachment_scores: dict[str, float] = field(default_factory=dict)
    love_language_primary: LoveLanguage = LoveLanguage.TIME
    love_language_secondary: LoveLanguage = LoveLanguage.WORDS
    love_language_scores: dict[str, float] = field(default_factory=dict)
    values: dict[str, float] = field(default_factory=dict)
    interests: list[str] = field(default_factory=list)
    deal_breakers: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "big_five": self.big_five.to_dict(),
            "attachment_style": self.attachment_style.value,
            "attachment_scores": {k: round(v, 2) for k, v in self.attachment_scores.items()},
            "love_language_primary": self.love_language_primary.value,
            "love_language_secondary": self.love_language_secondary.value,
            "love_language_scores": {k: round(v, 2) for k, v in self.love_language_scores.items()},
            "values": {k: round(v, 2) for k, v in self.values.items()},
            "interests": self.interests,
            "deal_breakers": self.deal_breakers,
        }


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _sigmoid_normalize(raw: float, midpoint: float = 0.0, steepness: float = 2.0) -> float:
    """Map raw score to 0-1 via sigmoid curve centered at midpoint."""
    return 1.0 / (1.0 + math.exp(-steepness * (raw - midpoint)))


class PersonalityEngine:
    """Processes questionnaire responses into a structured personality profile."""

    def score_big_five(self, answers: dict[str, float]) -> BigFiveScores:
        """
        Compute Big Five trait scores from questionnaire answers.
        Each answer is expected on a 1-5 Likert scale.
        Returns normalized 0-1 scores per trait.
        """
        scores = BigFiveScores()
        for trait, question_map in BIG_FIVE_MAP.items():
            raw_sum = 0.0
            count = 0
            for key, polarity in question_map:
                if key in answers:
                    val = (answers[key] - 3.0) / 2.0  # center and scale to -1..1
                    raw_sum += val * polarity
                    count += 1
            if count > 0:
                normalized = _sigmoid_normalize(raw_sum / count, midpoint=0.0, steepness=3.0)
                setattr(scores, trait, _clamp(normalized))
        return scores

    def detect_attachment_style(self, answers: dict[str, float]) -> tuple[AttachmentStyle, dict[str, float]]:
        """
        Classify attachment style from anxiety and avoidance dimensions.
        Returns style enum + dimension scores.
        """
        dimension_scores: dict[str, float] = {}
        for dimension, question_map in ATTACHMENT_QUESTIONS.items():
            raw_sum = 0.0
            count = 0
            for key, polarity in question_map:
                if key in answers:
                    val = (answers[key] - 3.0) / 2.0
                    raw_sum += val * polarity
                    count += 1
            dimension_scores[dimension] = _clamp(_sigmoid_normalize(raw_sum / max(count, 1))) if count else 0.5

        anxiety = dimension_scores.get("anxiety", 0.5)
        avoidance = dimension_scores.get("avoidance", 0.5)
        threshold = 0.5

        if anxiety < threshold and avoidance < threshold:
            style = AttachmentStyle.SECURE
        elif anxiety >= threshold and avoidance < threshold:
            style = AttachmentStyle.ANXIOUS
        elif anxiety < threshold and avoidance >= threshold:
            style = AttachmentStyle.AVOIDANT
        else:
            style = AttachmentStyle.DISORGANIZED

        return style, dimension_scores

    def identify_love_language(
        self, answers: dict[str, float]
    ) -> tuple[LoveLanguage, LoveLanguage, dict[str, float]]:
        """
        Rank love languages by questionnaire scores.
        Returns (primary, secondary, all scores).
        """
        lang_scores: dict[str, float] = {}
        for lang, keys in LOVE_LANGUAGE_QUESTIONS.items():
            total = 0.0
            count = 0
            for key in keys:
                if key in answers:
                    total += answers[key]
                    count += 1
            lang_scores[lang.value] = (total / max(count, 1)) / 5.0 if count else 0.0

        ranked = sorted(lang_scores.items(), key=lambda x: x[1], reverse=True)
        primary = LoveLanguage(ranked[0][0])
        secondary = LoveLanguage(ranked[1][0]) if len(ranked) > 1 else primary
        return primary, secondary, lang_scores

    def extract_values(self, answers: dict[str, float]) -> dict[str, float]:
        """Normalize value ratings to 0-1 scale."""
        values: dict[str, float] = {}
        for key in VALUES_KEYS:
            if key in answers:
                values[key] = _clamp(answers[key] / 5.0)
        return values

    def create_profile(
        self,
        user_id: str,
        answers: dict[str, float],
        interests: list[str] | None = None,
        deal_breakers: dict[str, Any] | None = None,
    ) -> PersonalityProfile:
        """Build a complete personality profile from raw questionnaire answers."""
        big_five = self.score_big_five(answers)
        attachment_style, attachment_scores = self.detect_attachment_style(answers)
        love_primary, love_secondary, love_scores = self.identify_love_language(answers)
        values = self.extract_values(answers)

        return PersonalityProfile(
            user_id=user_id,
            big_five=big_five,
            attachment_style=attachment_style,
            attachment_scores=attachment_scores,
            love_language_primary=love_primary,
            love_language_secondary=love_secondary,
            love_language_scores=love_scores,
            values=values,
            interests=interests or [],
            deal_breakers=deal_breakers or {},
        )

    def analyze_profile(self, profile: PersonalityProfile) -> dict[str, Any]:
        """Return a human-readable analysis of a profile."""
        bf = profile.big_five

        trait_descriptors = {
            "openness": ("imaginative and open to new ideas", "practical and conventional"),
            "conscientiousness": ("organized and disciplined", "flexible and spontaneous"),
            "extraversion": ("outgoing and energized by others", "introspective and reserved"),
            "agreeableness": ("warm and cooperative", "direct and competitive"),
            "neuroticism": ("emotionally sensitive", "emotionally resilient"),
        }

        traits_summary = {}
        for trait, (high_desc, low_desc) in trait_descriptors.items():
            score = getattr(bf, trait)
            if score >= 0.65:
                traits_summary[trait] = {"score": round(score, 2), "description": f"High — {high_desc}"}
            elif score <= 0.35:
                traits_summary[trait] = {"score": round(score, 2), "description": f"Low — {low_desc}"}
            else:
                traits_summary[trait] = {"score": round(score, 2), "description": "Moderate — balanced on this dimension"}

        attachment_desc = {
            AttachmentStyle.SECURE: "Comfortable with intimacy and independence. Trusting and communicative.",
            AttachmentStyle.ANXIOUS: "Craves closeness and reassurance. May worry about partner's availability.",
            AttachmentStyle.AVOIDANT: "Values independence highly. May struggle with emotional vulnerability.",
            AttachmentStyle.DISORGANIZED: "Mixed signals about closeness. Benefits from patient, consistent partners.",
        }

        return {
            "user_id": profile.user_id,
            "big_five_analysis": traits_summary,
            "attachment_style": {
                "style": profile.attachment_style.value,
                "description": attachment_desc[profile.attachment_style],
                "scores": profile.attachment_scores,
            },
            "love_language": {
                "primary": profile.love_language_primary.value,
                "secondary": profile.love_language_secondary.value,
                "scores": profile.love_language_scores,
            },
            "top_values": sorted(profile.values.items(), key=lambda x: x[1], reverse=True)[:5],
            "interests": profile.interests,
        }
