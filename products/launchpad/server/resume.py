from __future__ import annotations

import re
from dataclasses import dataclass, field


ACTION_VERBS = {
    "achieved", "administered", "analyzed", "built", "collaborated",
    "conducted", "created", "decreased", "delivered", "designed",
    "developed", "directed", "drove", "eliminated", "engineered",
    "established", "executed", "expanded", "generated", "grew",
    "implemented", "improved", "increased", "initiated", "launched",
    "led", "managed", "mentored", "migrated", "negotiated",
    "optimized", "orchestrated", "overhauled", "pioneered", "produced",
    "reduced", "refactored", "resolved", "revamped", "scaled",
    "spearheaded", "streamlined", "supervised", "transformed", "tripled",
}

SECTION_HEADERS = {
    "experience": ["experience", "work experience", "employment", "professional experience", "work history"],
    "education": ["education", "academic", "degrees", "certifications"],
    "skills": ["skills", "technical skills", "core competencies", "technologies", "proficiencies"],
    "summary": ["summary", "objective", "profile", "about", "professional summary"],
    "projects": ["projects", "portfolio", "personal projects"],
    "awards": ["awards", "honors", "achievements", "accomplishments"],
}


@dataclass
class ATSBreakdown:
    keyword_match: int = 0
    formatting: int = 0
    achievements: int = 0
    action_verbs: int = 0


@dataclass
class AnalysisResult:
    ats_score: int = 0
    breakdown: ATSBreakdown = field(default_factory=ATSBreakdown)
    improvements: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    sections_found: list[str] = field(default_factory=list)


class ResumeAnalyzer:
    def __init__(self, resume_text: str, job_description: str = ""):
        self.resume_text = resume_text
        self.resume_lower = resume_text.lower()
        self.job_description = job_description
        self.jd_lower = job_description.lower()
        self.resume_words = set(re.findall(r"\b[a-z]+(?:[+#.]?[a-z]*)*\b", self.resume_lower))

    def analyze(self) -> AnalysisResult:
        result = AnalysisResult()
        result.sections_found = self._detect_sections()
        result.breakdown.formatting = self._score_formatting(result.sections_found)
        result.breakdown.achievements = self._score_achievements()
        result.breakdown.action_verbs = self._score_action_verbs()

        kw_score, missing = self._score_keywords()
        result.breakdown.keyword_match = kw_score
        result.missing_keywords = missing

        result.ats_score = self._composite_score(result.breakdown)
        result.improvements = self._generate_improvements(result)
        return result

    def _detect_sections(self) -> list[str]:
        found: list[str] = []
        for section, variants in SECTION_HEADERS.items():
            for variant in variants:
                pattern = rf"(?:^|\n)\s*{re.escape(variant)}\s*[:\-—]?\s*(?:\n|$)"
                if re.search(pattern, self.resume_lower):
                    found.append(section)
                    break
        return found

    def _score_formatting(self, sections: list[str]) -> int:
        score = 0
        required = {"experience", "education", "skills"}
        found_required = required.intersection(sections)
        score += int(len(found_required) / len(required) * 40)

        lines = self.resume_text.strip().split("\n")
        non_empty = [l for l in lines if l.strip()]
        if 20 <= len(non_empty) <= 80:
            score += 20
        elif 10 <= len(non_empty) < 20:
            score += 10

        has_dates = bool(re.search(r"\b(19|20)\d{2}\b", self.resume_text))
        if has_dates:
            score += 15

        has_contact = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", self.resume_text))
        if has_contact:
            score += 10

        has_bullets = bool(re.search(r"(?:^|\n)\s*[•\-\*\u2022]", self.resume_text))
        if has_bullets:
            score += 15

        return min(score, 100)

    def _score_achievements(self) -> int:
        quantified = re.findall(
            r"\b\d+[%xX]?\b.*?(?:increase|decrease|reduce|improve|save|grow|generate|revenue|users|clients)",
            self.resume_lower,
        )
        dollar_amounts = re.findall(r"\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|k|m|b))?", self.resume_lower)
        percentage_claims = re.findall(r"\b\d+\s*%", self.resume_text)

        total = len(quantified) + len(dollar_amounts) + len(percentage_claims)
        if total >= 6:
            return 100
        if total >= 4:
            return 80
        if total >= 2:
            return 60
        if total >= 1:
            return 40
        return 15

    def _score_action_verbs(self) -> int:
        found = self.resume_words.intersection(ACTION_VERBS)
        count = len(found)
        if count >= 10:
            return 100
        if count >= 7:
            return 85
        if count >= 4:
            return 70
        if count >= 2:
            return 50
        return 20

    def _extract_jd_keywords(self) -> list[str]:
        if not self.job_description:
            return []
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "is", "are", "was", "were", "be",
            "been", "being", "have", "has", "had", "do", "does", "did",
            "will", "would", "could", "should", "may", "might", "can",
            "this", "that", "these", "those", "we", "you", "our", "your",
            "it", "its", "as", "from", "not", "if", "about", "up", "out",
            "all", "also", "into", "more", "other", "than", "then",
            "they", "their", "them", "who", "which", "what", "when",
            "where", "how", "no", "nor", "so", "very", "just", "such",
            "through", "over", "between", "each", "must", "able",
        }
        jd_words = re.findall(r"\b[a-z]+(?:[+#.]?[a-z]*)*\b", self.jd_lower)
        freq: dict[str, int] = {}
        for w in jd_words:
            if w not in stop_words and len(w) > 2:
                freq[w] = freq.get(w, 0) + 1
        return sorted(freq, key=freq.get, reverse=True)[:30]  # type: ignore[arg-type]

    def _score_keywords(self) -> tuple[int, list[str]]:
        keywords = self._extract_jd_keywords()
        if not keywords:
            return 50, []
        matched = [k for k in keywords if k in self.resume_words]
        missing = [k for k in keywords if k not in self.resume_words][:10]
        ratio = len(matched) / len(keywords)
        return min(int(ratio * 100), 100), missing

    @staticmethod
    def _composite_score(b: ATSBreakdown) -> int:
        return int(
            b.keyword_match * 0.35
            + b.formatting * 0.25
            + b.achievements * 0.20
            + b.action_verbs * 0.20
        )

    @staticmethod
    def _generate_improvements(result: AnalysisResult) -> list[str]:
        tips: list[str] = []

        if result.breakdown.keyword_match < 60 and result.missing_keywords:
            sample = ", ".join(result.missing_keywords[:5])
            tips.append(f"Add missing keywords from the job description: {sample}")

        if "experience" not in result.sections_found:
            tips.append("Add a clearly labeled 'Experience' section")
        if "education" not in result.sections_found:
            tips.append("Add a clearly labeled 'Education' section")
        if "skills" not in result.sections_found:
            tips.append("Add a 'Skills' section listing your technical and soft skills")

        if result.breakdown.achievements < 60:
            tips.append("Add quantified achievements (e.g., 'Reduced load time by 40%', 'Grew revenue $2M')")

        if result.breakdown.action_verbs < 60:
            tips.append("Start bullet points with strong action verbs (Led, Built, Designed, Optimized)")

        if result.breakdown.formatting < 60:
            tips.append("Improve formatting: use bullet points, consistent date formats, and clear section headers")

        if not tips:
            tips.append("Your resume looks strong! Consider tailoring it further to each specific job.")

        return tips

    def optimize(self) -> dict:
        analysis = self.analyze()
        suggestions: list[str] = []

        if analysis.missing_keywords:
            suggestions.append(
                f"Incorporate these keywords naturally into your experience bullets: "
                f"{', '.join(analysis.missing_keywords[:8])}"
            )

        if analysis.breakdown.achievements < 70:
            suggestions.append(
                "Convert responsibility statements into achievement statements. "
                "Instead of 'Responsible for database management', write "
                "'Optimized database queries, reducing average response time by 35%'."
            )

        if "summary" not in analysis.sections_found:
            suggestions.append(
                "Add a Professional Summary (2-3 sentences) at the top tailored to the target role."
            )

        if analysis.breakdown.action_verbs < 70:
            suggestions.append(
                "Replace passive language with action verbs: Led, Architected, Delivered, Scaled, Streamlined."
            )

        optimized_text = self.resume_text
        if "summary" not in analysis.sections_found and self.job_description:
            jd_keywords = self._extract_jd_keywords()[:5]
            summary_line = (
                f"\nProfessional Summary\n"
                f"Results-driven professional with expertise in {', '.join(jd_keywords[:3])}. "
                f"Proven track record of delivering high-impact solutions "
                f"in {', '.join(jd_keywords[3:5]) if len(jd_keywords) > 3 else 'cross-functional environments'}.\n"
            )
            lines = optimized_text.split("\n")
            insert_idx = min(2, len(lines))
            lines.insert(insert_idx, summary_line)
            optimized_text = "\n".join(lines)

        return {
            "original_score": analysis.ats_score,
            "optimized_resume": optimized_text,
            "changes_made": suggestions,
            "missing_keywords": analysis.missing_keywords,
            "projected_score_improvement": min(analysis.ats_score + 15, 100) - analysis.ats_score,
        }
