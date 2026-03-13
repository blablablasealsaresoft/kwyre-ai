"""
MatchingEngine — multi-dimensional compatibility scoring between personality profiles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .personality import AttachmentStyle, PersonalityProfile


@dataclass
class CompatibilityResult:
    overall_score: float
    category_scores: dict[str, float]
    breakdown: dict[str, Any]
    warnings: list[str]
    strengths: list[str]
    deal_breaker_pass: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 1),
            "category_scores": {k: round(v, 1) for k, v in self.category_scores.items()},
            "breakdown": self.breakdown,
            "warnings": self.warnings,
            "strengths": self.strengths,
            "deal_breaker_pass": self.deal_breaker_pass,
        }


# Weights must sum to 1.0
CATEGORY_WEIGHTS = {
    "trait_complementarity": 0.25,
    "shared_values": 0.30,
    "attachment_dynamics": 0.20,
    "love_language_alignment": 0.15,
    "deal_breaker_check": 0.10,
}

# Attachment pairing quality matrix: (style_a, style_b) → base score 0-100
ATTACHMENT_MATRIX: dict[tuple[AttachmentStyle, AttachmentStyle], float] = {
    (AttachmentStyle.SECURE, AttachmentStyle.SECURE): 95,
    (AttachmentStyle.SECURE, AttachmentStyle.ANXIOUS): 70,
    (AttachmentStyle.SECURE, AttachmentStyle.AVOIDANT): 65,
    (AttachmentStyle.SECURE, AttachmentStyle.DISORGANIZED): 55,
    (AttachmentStyle.ANXIOUS, AttachmentStyle.ANXIOUS): 45,
    (AttachmentStyle.ANXIOUS, AttachmentStyle.AVOIDANT): 25,
    (AttachmentStyle.ANXIOUS, AttachmentStyle.DISORGANIZED): 30,
    (AttachmentStyle.AVOIDANT, AttachmentStyle.AVOIDANT): 40,
    (AttachmentStyle.AVOIDANT, AttachmentStyle.DISORGANIZED): 35,
    (AttachmentStyle.DISORGANIZED, AttachmentStyle.DISORGANIZED): 20,
}

ATTACHMENT_WARNINGS = {
    (AttachmentStyle.ANXIOUS, AttachmentStyle.AVOIDANT): (
        "Anxious-avoidant trap: one partner pursues while the other withdraws. "
        "This dynamic can work with strong communication but requires awareness."
    ),
    (AttachmentStyle.DISORGANIZED, AttachmentStyle.DISORGANIZED): (
        "Both partners may struggle with trust and consistency. "
        "Professional support recommended for long-term success."
    ),
    (AttachmentStyle.ANXIOUS, AttachmentStyle.DISORGANIZED): (
        "The anxious partner's need for reassurance may clash with "
        "the disorganized partner's inconsistent availability."
    ),
}

DEAL_BREAKER_FIELDS = ["wants_children", "religion", "location", "smoking", "drinking"]


class MatchingEngine:
    """Computes multi-dimensional compatibility between two personality profiles."""

    def compute_compatibility(
        self, profile_a: PersonalityProfile, profile_b: PersonalityProfile
    ) -> CompatibilityResult:
        warnings: list[str] = []
        strengths: list[str] = []

        trait_score, trait_detail = self._score_traits(profile_a, profile_b, strengths)
        values_score, values_detail = self._score_values(profile_a, profile_b, strengths)
        attachment_score, attachment_detail = self._score_attachment(profile_a, profile_b, warnings, strengths)
        love_score, love_detail = self._score_love_language(profile_a, profile_b, strengths)
        deal_pass, deal_score, deal_detail = self._check_deal_breakers(profile_a, profile_b, warnings)

        category_scores = {
            "trait_complementarity": trait_score,
            "shared_values": values_score,
            "attachment_dynamics": attachment_score,
            "love_language_alignment": love_score,
            "deal_breaker_check": deal_score,
        }

        overall = sum(
            score * CATEGORY_WEIGHTS[cat] for cat, score in category_scores.items()
        )

        if not deal_pass:
            overall = min(overall, 35.0)
            warnings.insert(0, "Deal-breaker incompatibility detected — score capped.")

        return CompatibilityResult(
            overall_score=overall,
            category_scores=category_scores,
            breakdown={
                "trait_complementarity": trait_detail,
                "shared_values": values_detail,
                "attachment_dynamics": attachment_detail,
                "love_language_alignment": love_detail,
                "deal_breaker_check": deal_detail,
            },
            warnings=warnings,
            strengths=strengths,
            deal_breaker_pass=deal_pass,
        )

    def find_top_matches(
        self,
        profile: PersonalityProfile,
        pool: list[PersonalityProfile],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Score profile against a pool and return top matches sorted by compatibility."""
        results = []
        for candidate in pool:
            if candidate.user_id == profile.user_id:
                continue
            result = self.compute_compatibility(profile, candidate)
            results.append({
                "user_id": candidate.user_id,
                "compatibility": result.to_dict(),
            })
        results.sort(key=lambda r: r["compatibility"]["overall_score"], reverse=True)
        return results[:limit]

    def _score_traits(
        self, a: PersonalityProfile, b: PersonalityProfile, strengths: list[str]
    ) -> tuple[float, dict[str, Any]]:
        """
        Complementary traits get bonuses, similar traits on some dimensions are good.
        Extraversion: complementary is better (introvert + extrovert).
        Conscientiousness: similarity is better.
        Openness: similarity is better.
        Agreeableness: both high is best.
        Neuroticism: large gaps penalized.
        """
        bf_a, bf_b = a.big_five, b.big_five
        detail: dict[str, Any] = {}
        total = 0.0

        # Extraversion — complementarity bonus
        ext_diff = abs(bf_a.extraversion - bf_b.extraversion)
        ext_score = 50 + ext_diff * 50  # more different = higher score
        detail["extraversion"] = {"score": round(ext_score, 1), "mode": "complementary"}
        if ext_diff > 0.4:
            strengths.append("Complementary social energy — one recharges while the other engages.")
        total += ext_score

        # Conscientiousness — similarity
        con_diff = abs(bf_a.conscientiousness - bf_b.conscientiousness)
        con_score = 100 - con_diff * 80
        detail["conscientiousness"] = {"score": round(con_score, 1), "mode": "similarity"}
        if con_diff < 0.2:
            strengths.append("Similar organizational styles reduce daily friction.")
        total += con_score

        # Openness — similarity
        open_diff = abs(bf_a.openness - bf_b.openness)
        open_score = 100 - open_diff * 70
        detail["openness"] = {"score": round(open_score, 1), "mode": "similarity"}
        total += open_score

        # Agreeableness — both high is ideal
        agree_avg = (bf_a.agreeableness + bf_b.agreeableness) / 2
        agree_score = agree_avg * 100
        detail["agreeableness"] = {"score": round(agree_score, 1), "mode": "mutual_high"}
        if agree_avg > 0.7:
            strengths.append("Both partners are naturally warm and cooperative.")
        total += agree_score

        # Neuroticism — large gaps create tension
        neuro_diff = abs(bf_a.neuroticism - bf_b.neuroticism)
        neuro_score = 100 - neuro_diff * 100
        detail["neuroticism"] = {"score": round(neuro_score, 1), "mode": "gap_penalty"}
        total += neuro_score

        avg_score = total / 5
        return avg_score, detail

    def _score_values(
        self, a: PersonalityProfile, b: PersonalityProfile, strengths: list[str]
    ) -> tuple[float, dict[str, Any]]:
        """Shared values score — overlap on top priorities weighted heavily."""
        if not a.values or not b.values:
            return 50.0, {"note": "Insufficient values data"}

        all_keys = set(a.values.keys()) | set(b.values.keys())
        if not all_keys:
            return 50.0, {"note": "No values provided"}

        weighted_sum = 0.0
        total_weight = 0.0
        shared_high: list[str] = []
        conflicts: list[str] = []
        per_value: dict[str, float] = {}

        for key in all_keys:
            val_a = a.values.get(key, 0.5)
            val_b = b.values.get(key, 0.5)
            importance = (val_a + val_b) / 2  # higher mutual importance = higher weight
            diff = abs(val_a - val_b)
            alignment = 1.0 - diff
            weight = 0.5 + importance  # base weight + importance bonus
            weighted_sum += alignment * weight * 100
            total_weight += weight
            per_value[key] = round(alignment * 100, 1)

            if val_a >= 0.7 and val_b >= 0.7:
                shared_high.append(key.replace("_", " "))
            elif diff > 0.5 and (val_a >= 0.7 or val_b >= 0.7):
                conflicts.append(key.replace("_", " "))

        score = weighted_sum / max(total_weight, 1)

        if shared_high:
            strengths.append(f"Shared priorities: {', '.join(shared_high[:3])}.")

        detail = {"per_value": per_value, "shared_high_values": shared_high, "value_conflicts": conflicts}
        return min(score, 100.0), detail

    def _score_attachment(
        self,
        a: PersonalityProfile,
        b: PersonalityProfile,
        warnings: list[str],
        strengths: list[str],
    ) -> tuple[float, dict[str, Any]]:
        """Score attachment style compatibility using the pairing matrix."""
        pair = (a.attachment_style, b.attachment_style)
        reverse_pair = (b.attachment_style, a.attachment_style)

        score = ATTACHMENT_MATRIX.get(pair) or ATTACHMENT_MATRIX.get(reverse_pair, 50.0)

        warning_msg = ATTACHMENT_WARNINGS.get(pair) or ATTACHMENT_WARNINGS.get(reverse_pair)
        if warning_msg:
            warnings.append(warning_msg)

        if a.attachment_style == AttachmentStyle.SECURE or b.attachment_style == AttachmentStyle.SECURE:
            strengths.append("At least one secure attachment style — strong foundation for trust.")

        if a.attachment_style == AttachmentStyle.SECURE and b.attachment_style == AttachmentStyle.SECURE:
            strengths.append("Both securely attached — excellent baseline for emotional safety.")

        detail = {
            "style_a": a.attachment_style.value,
            "style_b": b.attachment_style.value,
            "pairing_score": score,
        }
        return score, detail

    def _score_love_language(
        self, a: PersonalityProfile, b: PersonalityProfile, strengths: list[str]
    ) -> tuple[float, dict[str, Any]]:
        """
        Score love language alignment.
        Primary match = high score. Primary-secondary cross-match = moderate.
        """
        score = 0.0

        if a.love_language_primary == b.love_language_primary:
            score = 90.0
            strengths.append(
                f"Both speak {a.love_language_primary.value.replace('_', ' ')} — natural emotional connection."
            )
        elif a.love_language_primary == b.love_language_secondary:
            score = 70.0
        elif a.love_language_secondary == b.love_language_primary:
            score = 65.0
        elif a.love_language_secondary == b.love_language_secondary:
            score = 55.0
        else:
            score = 35.0

        # Boost if score distributions are similar
        if a.love_language_scores and b.love_language_scores:
            common_keys = set(a.love_language_scores.keys()) & set(b.love_language_scores.keys())
            if common_keys:
                diffs = [abs(a.love_language_scores[k] - b.love_language_scores[k]) for k in common_keys]
                avg_diff = sum(diffs) / len(diffs)
                distribution_bonus = (1.0 - avg_diff) * 15
                score = min(score + distribution_bonus, 100.0)

        detail = {
            "primary_a": a.love_language_primary.value,
            "primary_b": b.love_language_primary.value,
            "secondary_a": a.love_language_secondary.value,
            "secondary_b": b.love_language_secondary.value,
        }
        return score, detail

    def _check_deal_breakers(
        self, a: PersonalityProfile, b: PersonalityProfile, warnings: list[str]
    ) -> tuple[bool, float, dict[str, Any]]:
        """
        Hard filter on deal-breaker fields. Returns (pass, score, detail).
        Missing fields are treated as flexible / no preference.
        """
        if not a.deal_breakers and not b.deal_breakers:
            return True, 80.0, {"note": "No deal-breakers specified"}

        conflicts: list[str] = []
        checked = 0
        passed = 0

        for field_name in DEAL_BREAKER_FIELDS:
            val_a = a.deal_breakers.get(field_name)
            val_b = b.deal_breakers.get(field_name)
            if val_a is None or val_b is None:
                continue
            checked += 1

            if field_name == "wants_children":
                if val_a == val_b:
                    passed += 1
                else:
                    conflicts.append(f"Children: {val_a} vs {val_b}")
            elif field_name == "location":
                if val_a == val_b or val_a == "flexible" or val_b == "flexible":
                    passed += 1
                else:
                    conflicts.append(f"Location: {val_a} vs {val_b}")
            else:
                if val_a == val_b:
                    passed += 1
                elif isinstance(val_a, str) and isinstance(val_b, str):
                    if val_a.lower() == "no_preference" or val_b.lower() == "no_preference":
                        passed += 1
                    else:
                        conflicts.append(f"{field_name}: {val_a} vs {val_b}")
                else:
                    conflicts.append(f"{field_name}: {val_a} vs {val_b}")

        if conflicts:
            for c in conflicts:
                warnings.append(f"Deal-breaker conflict — {c}")

        if checked == 0:
            return True, 80.0, {"note": "No overlapping deal-breaker fields to compare"}

        all_pass = len(conflicts) == 0
        score = (passed / checked) * 100 if checked else 80.0

        return all_pass, score, {"checked": checked, "passed": passed, "conflicts": conflicts}
