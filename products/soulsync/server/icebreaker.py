"""
IcebreakerGenerator — personalized conversation starters based on profile overlap and contrast.
"""

from __future__ import annotations

import random
from typing import Any

from .personality import AttachmentStyle, LoveLanguage, PersonalityProfile


class IcebreakerGenerator:
    """Generates context-aware conversation starters from two personality profiles."""

    def generate(
        self, profile_a: PersonalityProfile, profile_b: PersonalityProfile, count: int = 5
    ) -> list[dict[str, str]]:
        """
        Produce personalized icebreakers referencing specific profile data.
        Returns list of {category, prompt} dicts.
        """
        candidates: list[dict[str, str]] = []

        candidates.extend(self._from_shared_interests(profile_a, profile_b))
        candidates.extend(self._from_complementary_traits(profile_a, profile_b))
        candidates.extend(self._from_shared_values(profile_a, profile_b))
        candidates.extend(self._from_love_language(profile_a, profile_b))
        candidates.extend(self._from_unique_aspects(profile_a, profile_b))
        candidates.extend(self._from_attachment_awareness(profile_a, profile_b))

        if len(candidates) <= count:
            return candidates

        # Ensure variety across categories
        by_category: dict[str, list[dict[str, str]]] = {}
        for c in candidates:
            by_category.setdefault(c["category"], []).append(c)

        selected: list[dict[str, str]] = []
        categories = list(by_category.keys())
        random.shuffle(categories)

        for cat in categories:
            if len(selected) >= count:
                break
            items = by_category[cat]
            selected.append(random.choice(items))

        remaining = [c for c in candidates if c not in selected]
        random.shuffle(remaining)
        while len(selected) < count and remaining:
            selected.append(remaining.pop())

        return selected[:count]

    def _from_shared_interests(
        self, a: PersonalityProfile, b: PersonalityProfile
    ) -> list[dict[str, str]]:
        shared = set(a.interests) & set(b.interests)
        results: list[dict[str, str]] = []
        for interest in shared:
            clean = interest.replace("_", " ")
            results.append({
                "category": "shared_interest",
                "prompt": (
                    f"You both listed {clean} as an interest. "
                    f"What first got you into {clean}, and what keeps you coming back?"
                ),
            })
            results.append({
                "category": "shared_interest",
                "prompt": (
                    f"If you could plan the perfect {clean} day together, "
                    f"what would it look like?"
                ),
            })
        return results

    def _from_complementary_traits(
        self, a: PersonalityProfile, b: PersonalityProfile
    ) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        bf_a, bf_b = a.big_five, b.big_five

        ext_diff = bf_a.extraversion - bf_b.extraversion
        if abs(ext_diff) > 0.3:
            more_ext = "you" if ext_diff > 0 else "they"
            less_ext = "they" if ext_diff > 0 else "you"
            results.append({
                "category": "complementary_trait",
                "prompt": (
                    f"One of you is more outgoing and the other more introspective — "
                    f"what's your ideal Friday night? Big party, cozy night in, or something else entirely?"
                ),
            })

        open_diff = bf_a.openness - bf_b.openness
        if abs(open_diff) > 0.3:
            results.append({
                "category": "complementary_trait",
                "prompt": (
                    "You balance each other on the adventure-stability spectrum. "
                    "What's the most spontaneous thing you've done that surprised even you?"
                ),
            })

        if bf_a.conscientiousness > 0.7 and bf_b.conscientiousness > 0.7:
            results.append({
                "category": "complementary_trait",
                "prompt": (
                    "You're both planners. Do you plan vacations down to the hour, "
                    "or is there one area of life where you let chaos reign?"
                ),
            })

        if bf_a.agreeableness > 0.7 and bf_b.agreeableness > 0.7:
            results.append({
                "category": "complementary_trait",
                "prompt": (
                    "You both value harmony. What's a hill you'd actually die on — "
                    "the one topic where you won't budge?"
                ),
            })

        return results

    def _from_shared_values(
        self, a: PersonalityProfile, b: PersonalityProfile
    ) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        shared_high: list[str] = []

        for key in a.values:
            if key in b.values and a.values[key] >= 0.7 and b.values[key] >= 0.7:
                shared_high.append(key)

        value_prompts = {
            "career_ambition": (
                "You're both career-driven. What does 'making it' actually look like for you — "
                "title, impact, freedom, or something else?"
            ),
            "family_priority": (
                "Family matters to both of you. What's a family tradition you'd want to "
                "bring into a future relationship?"
            ),
            "adventure_seeking": (
                "You're both adventure seekers. What's on your bucket list that "
                "you haven't done yet but absolutely will?"
            ),
            "stability_preference": (
                "You both value stability. What does a 'settled' life look like to you — "
                "and does it ever feel boring?"
            ),
            "personal_growth": (
                "Growth is important to both of you. What's something you've been working on "
                "about yourself recently?"
            ),
            "spirituality": (
                "Spirituality resonates with both of you. Is it a daily practice, "
                "a quiet belief, or something you're still exploring?"
            ),
            "creativity_expression": (
                "You both value creative expression. What's a creative project you've been "
                "meaning to start or get back to?"
            ),
            "health_fitness": (
                "Health and fitness matter to you both. Are you a morning run person, "
                "a gym rat, a yoga devotee, or something totally different?"
            ),
        }

        for val in shared_high:
            if val in value_prompts:
                results.append({"category": "shared_value", "prompt": value_prompts[val]})

        return results

    def _from_love_language(
        self, a: PersonalityProfile, b: PersonalityProfile
    ) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []

        lang_prompts = {
            LoveLanguage.WORDS: (
                "Words matter to you. What's the best compliment you've ever received — "
                "the one that stuck with you?"
            ),
            LoveLanguage.ACTS: (
                "Actions speak loudest for you. What's a small act of service "
                "that would absolutely make your week?"
            ),
            LoveLanguage.GIFTS: (
                "Thoughtful gifts resonate with you. What's the most meaningful gift "
                "you've ever given or received, and why?"
            ),
            LoveLanguage.TIME: (
                "Quality time is your thing. What's an activity where you completely "
                "lose track of time when sharing it with someone?"
            ),
            LoveLanguage.TOUCH: (
                "Physical connection matters to you. Are you a 'hold hands walking down the street' "
                "person or more of a 'cozy on the couch' type?"
            ),
        }

        if a.love_language_primary == b.love_language_primary:
            lang = a.love_language_primary
            results.append({
                "category": "love_language",
                "prompt": (
                    f"You both express love through {lang.value.replace('_', ' ')}. "
                    f"{lang_prompts.get(lang, 'How does that show up in your daily life?')}"
                ),
            })
        else:
            results.append({
                "category": "love_language",
                "prompt": (
                    f"You express love differently — one through "
                    f"{a.love_language_primary.value.replace('_', ' ')} and the other through "
                    f"{b.love_language_primary.value.replace('_', ' ')}. "
                    f"How do you most like to feel appreciated?"
                ),
            })

        return results

    def _from_unique_aspects(
        self, a: PersonalityProfile, b: PersonalityProfile
    ) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        unique_a = set(a.interests) - set(b.interests)
        unique_b = set(b.interests) - set(a.interests)

        if unique_a:
            interest = random.choice(list(unique_a)).replace("_", " ")
            results.append({
                "category": "unique_aspect",
                "prompt": (
                    f"One of you is into {interest} — tell the other person "
                    f"what makes it fascinating. Convert them in 30 seconds."
                ),
            })

        if unique_b:
            interest = random.choice(list(unique_b)).replace("_", " ")
            results.append({
                "category": "unique_aspect",
                "prompt": (
                    f"One of you is passionate about {interest}. "
                    f"What's the one thing about it that most people don't understand?"
                ),
            })

        return results

    def _from_attachment_awareness(
        self, a: PersonalityProfile, b: PersonalityProfile
    ) -> list[dict[str, str]]:
        """Gentle prompts that touch on relational style without clinical language."""
        results: list[dict[str, str]] = []

        if a.attachment_style == AttachmentStyle.SECURE and b.attachment_style == AttachmentStyle.SECURE:
            results.append({
                "category": "connection_style",
                "prompt": (
                    "You both seem grounded in relationships. What's the best piece of "
                    "relationship advice you've ever received?"
                ),
            })
        elif AttachmentStyle.ANXIOUS in (a.attachment_style, b.attachment_style):
            results.append({
                "category": "connection_style",
                "prompt": (
                    "What does feeling 'safe' in a relationship look like to you? "
                    "Is it words, consistency, or something else?"
                ),
            })
        elif AttachmentStyle.AVOIDANT in (a.attachment_style, b.attachment_style):
            results.append({
                "category": "connection_style",
                "prompt": (
                    "How do you balance needing space with wanting closeness? "
                    "Is there a sweet spot you've found?"
                ),
            })

        return results


def generate_coaching_advice(
    profile_a: PersonalityProfile,
    profile_b: PersonalityProfile,
    compatibility: dict[str, Any],
) -> list[dict[str, str]]:
    """Generate relationship coaching tips based on match context."""
    tips: list[dict[str, str]] = []
    warnings = compatibility.get("warnings", [])
    strengths = compatibility.get("strengths", [])
    score = compatibility.get("overall_score", 50)

    if score >= 80:
        tips.append({
            "category": "general",
            "advice": (
                "You have strong natural compatibility. Focus on maintaining curiosity about "
                "each other rather than assuming you already 'get' everything."
            ),
        })
    elif score >= 60:
        tips.append({
            "category": "general",
            "advice": (
                "You have solid compatibility with room to grow. The differences between you "
                "can become strengths if you approach them with curiosity rather than frustration."
            ),
        })
    else:
        tips.append({
            "category": "general",
            "advice": (
                "Your profiles show some friction areas. This doesn't mean it can't work — "
                "but it means intentional communication will be especially important."
            ),
        })

    # Attachment-specific advice
    styles = {profile_a.attachment_style, profile_b.attachment_style}
    if AttachmentStyle.ANXIOUS in styles and AttachmentStyle.AVOIDANT in styles:
        tips.append({
            "category": "attachment",
            "advice": (
                "One of you may need more reassurance while the other needs more space. "
                "Establish a 'check-in' ritual — a brief daily moment to connect that satisfies "
                "the need for closeness without overwhelming the need for independence."
            ),
        })
    elif AttachmentStyle.ANXIOUS in styles:
        tips.append({
            "category": "attachment",
            "advice": (
                "Proactive reassurance goes a long way. Small, consistent gestures — "
                "a good-morning text, a 'thinking of you' — build trust more than grand gestures."
            ),
        })
    elif AttachmentStyle.AVOIDANT in styles:
        tips.append({
            "category": "attachment",
            "advice": (
                "Respect each other's need for autonomy, but schedule intentional together-time. "
                "Having it on the calendar removes the pressure of spontaneous emotional bids."
            ),
        })

    # Love language advice
    if profile_a.love_language_primary != profile_b.love_language_primary:
        lang_a = profile_a.love_language_primary.value.replace("_", " ")
        lang_b = profile_b.love_language_primary.value.replace("_", " ")
        tips.append({
            "category": "love_language",
            "advice": (
                f"You speak different love languages ({lang_a} vs {lang_b}). "
                f"Learn to 'translate' — express love in their language, not just yours. "
                f"It feels unnatural at first but becomes second nature."
            ),
        })

    # Values-based advice
    cat_scores = compatibility.get("category_scores", {})
    if cat_scores.get("shared_values", 100) < 60:
        tips.append({
            "category": "values",
            "advice": (
                "Your values don't fully align. Have an honest conversation about priorities — "
                "not to convince each other, but to understand where flexibility exists "
                "and where it doesn't."
            ),
        })

    if any("deal-breaker" in w.lower() for w in warnings):
        tips.append({
            "category": "deal_breakers",
            "advice": (
                "There are potential deal-breaker conflicts. Address these directly and early. "
                "It's better to have a hard conversation now than a harder one later."
            ),
        })

    return tips
