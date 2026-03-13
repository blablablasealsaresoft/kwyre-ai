from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


@dataclass
class JobPosting:
    id: str
    title: str
    company: str
    description: str
    required_skills: list[str] = field(default_factory=list)
    location: str = "remote"
    salary_min: int = 0
    salary_max: int = 0
    experience_years: int = 0
    industry: str = ""


@dataclass
class CandidateProfile:
    skills: list[str] = field(default_factory=list)
    experience_years: int = 0
    preferred_locations: list[str] = field(default_factory=list)
    salary_min: int = 0
    salary_max: int = 0
    preferred_industries: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    job: JobPosting
    overall_score: float = 0.0
    skill_score: float = 0.0
    location_score: float = 0.0
    salary_score: float = 0.0
    experience_score: float = 0.0
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)


SAMPLE_JOBS = [
    JobPosting(
        id="job-001",
        title="Senior Software Engineer",
        company="TechCorp",
        description="Build scalable backend services using Python, Go, and Kubernetes. Experience with distributed systems and cloud infrastructure required.",
        required_skills=["python", "go", "kubernetes", "distributed systems", "aws", "docker", "sql", "rest api"],
        location="remote",
        salary_min=150000,
        salary_max=200000,
        experience_years=5,
        industry="technology",
    ),
    JobPosting(
        id="job-002",
        title="Full Stack Developer",
        company="StartupXYZ",
        description="Join a fast-paced startup building the next generation of fintech products. React, Node.js, and PostgreSQL experience needed.",
        required_skills=["react", "node.js", "typescript", "postgresql", "graphql", "aws", "git"],
        location="new york",
        salary_min=120000,
        salary_max=170000,
        experience_years=3,
        industry="fintech",
    ),
    JobPosting(
        id="job-003",
        title="Data Scientist",
        company="DataDriven Inc",
        description="Apply machine learning to solve real-world business problems. Strong Python, SQL, and statistical modeling skills required.",
        required_skills=["python", "sql", "machine learning", "statistics", "pandas", "scikit-learn", "tensorflow"],
        location="san francisco",
        salary_min=140000,
        salary_max=190000,
        experience_years=3,
        industry="technology",
    ),
    JobPosting(
        id="job-004",
        title="Product Manager",
        company="BigCo",
        description="Own the product roadmap for our enterprise platform. Experience with B2B SaaS, agile methodologies, and data-driven decision making.",
        required_skills=["product management", "agile", "sql", "analytics", "roadmap planning", "stakeholder management"],
        location="remote",
        salary_min=130000,
        salary_max=175000,
        experience_years=4,
        industry="saas",
    ),
    JobPosting(
        id="job-005",
        title="DevOps Engineer",
        company="CloudNative Co",
        description="Design and maintain CI/CD pipelines, infrastructure as code, and monitoring systems. Terraform, AWS, and Kubernetes expertise required.",
        required_skills=["terraform", "aws", "kubernetes", "docker", "ci/cd", "linux", "python", "monitoring"],
        location="remote",
        salary_min=140000,
        salary_max=185000,
        experience_years=4,
        industry="technology",
    ),
    JobPosting(
        id="job-006",
        title="Frontend Engineer",
        company="DesignFirst",
        description="Build beautiful, accessible, performant user interfaces. Deep React/TypeScript expertise and an eye for design required.",
        required_skills=["react", "typescript", "css", "html", "accessibility", "figma", "testing"],
        location="los angeles",
        salary_min=130000,
        salary_max=175000,
        experience_years=3,
        industry="design",
    ),
    JobPosting(
        id="job-007",
        title="Machine Learning Engineer",
        company="AI Solutions",
        description="Deploy and optimize ML models at scale. Experience with PyTorch, MLOps, and production ML systems.",
        required_skills=["python", "pytorch", "mlops", "docker", "kubernetes", "sql", "aws", "model optimization"],
        location="remote",
        salary_min=160000,
        salary_max=220000,
        experience_years=4,
        industry="artificial intelligence",
    ),
    JobPosting(
        id="job-008",
        title="Sales Development Representative",
        company="SaaS Growth",
        description="Drive pipeline growth through outbound prospecting. CRM experience and strong communication skills essential.",
        required_skills=["salesforce", "cold outreach", "crm", "communication", "lead generation", "pipeline management"],
        location="chicago",
        salary_min=60000,
        salary_max=90000,
        experience_years=1,
        industry="saas",
    ),
]


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9+#./\s]", "", text.lower()).strip()


def _tokenize(text: str) -> set[str]:
    return {_normalize(w) for w in re.split(r"[,;|\n]+", text) if w.strip()}


class JobMatcher:
    def __init__(self, jobs: list[JobPosting] | None = None):
        self.jobs = jobs or SAMPLE_JOBS

    def match(self, profile: CandidateProfile, limit: int = 10) -> list[dict]:
        candidate_skills = {_normalize(s) for s in profile.skills}
        results: list[MatchResult] = []

        for job in self.jobs:
            result = MatchResult(job=job)

            job_skills = {_normalize(s) for s in job.required_skills}
            result.matched_skills = sorted(candidate_skills & job_skills)
            result.missing_skills = sorted(job_skills - candidate_skills)
            result.skill_score = self._skill_similarity(candidate_skills, job_skills, job.description)
            result.location_score = self._location_score(profile.preferred_locations, job.location)
            result.salary_score = self._salary_score(profile.salary_min, profile.salary_max, job.salary_min, job.salary_max)
            result.experience_score = self._experience_score(profile.experience_years, job.experience_years)

            result.overall_score = round(
                result.skill_score * 0.45
                + result.location_score * 0.15
                + result.salary_score * 0.20
                + result.experience_score * 0.20,
                1,
            )

            results.append(result)

        results.sort(key=lambda r: r.overall_score, reverse=True)

        return [
            {
                "job_id": r.job.id,
                "title": r.job.title,
                "company": r.job.company,
                "location": r.job.location,
                "salary_range": f"${r.job.salary_min:,}–${r.job.salary_max:,}" if r.job.salary_min else "Not listed",
                "overall_score": r.overall_score,
                "breakdown": {
                    "skill_match": round(r.skill_score, 1),
                    "location_fit": round(r.location_score, 1),
                    "salary_fit": round(r.salary_score, 1),
                    "experience_fit": round(r.experience_score, 1),
                },
                "matched_skills": r.matched_skills,
                "missing_skills": r.missing_skills,
            }
            for r in results[:limit]
        ]

    def _skill_similarity(self, candidate: set[str], required: set[str], description: str) -> float:
        if not required:
            return 50.0
        direct_overlap = len(candidate & required)
        direct_score = direct_overlap / len(required) * 100

        desc_tokens = set(_normalize(description).split())
        candidate_in_desc = len({s for s in candidate if s in desc_tokens or any(s in t for t in desc_tokens)})
        bonus = min(candidate_in_desc * 3, 15)

        return min(direct_score + bonus, 100.0)

    @staticmethod
    def _location_score(preferred: list[str], job_location: str) -> float:
        if not preferred:
            return 80.0
        job_loc = _normalize(job_location)
        if job_loc == "remote":
            return 100.0
        for pref in preferred:
            if _normalize(pref) == job_loc or _normalize(pref) in job_loc or job_loc in _normalize(pref):
                return 100.0
            if _normalize(pref) == "remote":
                return 60.0
        return 30.0

    @staticmethod
    def _salary_score(cand_min: int, cand_max: int, job_min: int, job_max: int) -> float:
        if not cand_min and not cand_max:
            return 70.0
        if not job_min and not job_max:
            return 60.0
        overlap_start = max(cand_min, job_min)
        overlap_end = min(cand_max or math.inf, job_max or math.inf)
        if overlap_start <= overlap_end:
            return 100.0
        gap = overlap_start - overlap_end
        max_range = max(job_max - job_min, 1)
        penalty = min(gap / max_range * 100, 70)
        return max(100 - penalty, 30.0)

    @staticmethod
    def _experience_score(candidate_years: int, required_years: int) -> float:
        if not required_years:
            return 80.0
        diff = candidate_years - required_years
        if diff >= 0:
            return min(100.0, 90.0 + diff * 2)
        if diff >= -1:
            return 75.0
        if diff >= -2:
            return 55.0
        return 30.0
