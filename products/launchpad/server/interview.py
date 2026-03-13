from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class InterviewQuestion:
    type: str
    question: str
    model_answer: str
    difficulty: str = "medium"


BEHAVIORAL_QUESTIONS = [
    {
        "q": "Tell me about a time you had to deal with a difficult stakeholder.",
        "a": (
            "Situation: A product manager kept changing requirements mid-sprint, causing delays. "
            "Task: I needed to establish a process that respected both engineering capacity and business needs. "
            "Action: I scheduled a weekly alignment meeting, introduced a change-request form with impact estimates, "
            "and presented data on how mid-sprint changes affected velocity. "
            "Result: Unplanned changes dropped 70%, sprint completion rate improved from 65% to 92%."
        ),
    },
    {
        "q": "Describe a situation where you failed and what you learned.",
        "a": (
            "Situation: I pushed a database migration to production without adequate testing on a staging environment. "
            "Task: The migration locked a critical table for 12 minutes during peak traffic. "
            "Action: I immediately rolled back, wrote a post-mortem, and implemented a pre-deploy checklist "
            "including mandatory staging runs and lock-duration estimates for all DDL changes. "
            "Result: Zero migration-related incidents in the following 18 months. The checklist was adopted team-wide."
        ),
    },
    {
        "q": "Tell me about a time you led a project with ambiguous requirements.",
        "a": (
            "Situation: Leadership asked for a 'customer health dashboard' with no specifications. "
            "Task: Deliver a useful product without clear requirements. "
            "Action: I interviewed 5 customer success managers to identify their top pain points, "
            "built a prototype in 1 week, ran 3 feedback rounds, and iterated to a final design. "
            "Result: Dashboard reduced churn investigation time by 50% and was cited in 2 enterprise renewals."
        ),
    },
    {
        "q": "Give an example of when you had to make a decision with incomplete information.",
        "a": (
            "Situation: Our primary API vendor announced a 300% price increase effective in 30 days. "
            "Task: Decide whether to migrate vendors, build in-house, or negotiate. "
            "Action: I spent 2 days benchmarking 3 alternatives, estimated migration effort at 2 weeks, "
            "and negotiated a 6-month extension with the current vendor at a 50% increase. "
            "Result: Bought time to migrate properly, saving $180K annually on the new vendor."
        ),
    },
    {
        "q": "Describe how you handled a conflict within your team.",
        "a": (
            "Situation: Two senior engineers disagreed on whether to use microservices or a modular monolith. "
            "Task: Resolve the conflict before it blocked the project. "
            "Action: I facilitated a structured debate where each side presented trade-offs with data, "
            "then we scored options against our constraints (team size, timeline, ops maturity). "
            "Result: Team aligned on the modular monolith with clear extraction boundaries. "
            "Both engineers felt heard, and we shipped on schedule."
        ),
    },
]

ROLE_QUESTIONS: dict[str, dict[str, list[dict[str, str]]]] = {
    "software_engineer": {
        "technical": [
            {
                "q": "Explain how you would design a rate limiter for a high-traffic API.",
                "a": (
                    "I'd use a sliding window counter backed by Redis. Each API key gets a sorted set "
                    "where members are request timestamps. On each request: remove entries outside the window, "
                    "count remaining, reject if over limit. For distributed systems, I'd use Redis Cluster "
                    "with Lua scripts for atomicity. Fallback: token bucket algorithm for smoother burst handling."
                ),
            },
            {
                "q": "How would you debug a memory leak in a production service?",
                "a": (
                    "First, confirm via monitoring (RSS growth over time). Take heap snapshots at intervals. "
                    "Compare snapshots to identify growing object types. Common culprits: unbounded caches, "
                    "event listener leaks, unclosed connections. I'd use pprof (Go), heapdump (Node), or "
                    "tracemalloc (Python). Fix, deploy to canary, verify RSS stabilizes."
                ),
            },
            {
                "q": "Walk me through how you'd migrate a monolith to microservices.",
                "a": (
                    "Start with the Strangler Fig pattern. Identify bounded contexts via domain analysis. "
                    "Extract the least-coupled, highest-value service first. Put an API gateway in front "
                    "to route traffic. Use event-driven communication (not synchronous chains). "
                    "Each service owns its data. Migrate incrementally — never big-bang."
                ),
            },
        ],
        "situational": [
            {
                "q": "Your team discovers a critical security vulnerability 2 days before a major release. What do you do?",
                "a": (
                    "Immediately assess severity (CVSS score, exploitability, blast radius). If critical: "
                    "delay the release, fix the vulnerability, get a security review, and deploy the patch. "
                    "Communicate transparently to stakeholders with a revised timeline. "
                    "After: add the vulnerability class to our security scanning pipeline."
                ),
            },
        ],
    },
    "product_manager": {
        "technical": [
            {
                "q": "How would you prioritize a backlog with 50+ feature requests?",
                "a": (
                    "Apply RICE scoring (Reach, Impact, Confidence, Effort). Group by strategic themes. "
                    "Validate top candidates with customer data (usage analytics, NPS verbatims, sales feedback). "
                    "Present a ranked list to leadership with trade-off context. "
                    "Ship the highest RICE items first, revisit quarterly."
                ),
            },
            {
                "q": "Describe your approach to defining success metrics for a new feature.",
                "a": (
                    "Start with the business objective (revenue, retention, engagement). Define a primary metric "
                    "(north star) and 2-3 guardrail metrics to ensure we don't optimize one thing at the expense "
                    "of another. Set targets using baselines + benchmarks. Instrument tracking before launch. "
                    "Review results at 1 week, 1 month, 1 quarter."
                ),
            },
        ],
        "situational": [
            {
                "q": "Engineering says a feature you promised to a key customer will take 3x longer than expected. What do you do?",
                "a": (
                    "First, understand the technical complexity driving the estimate. Explore scope reduction: "
                    "can we deliver 80% of the value in the original timeline? Communicate proactively "
                    "to the customer with a revised plan and interim solutions. "
                    "Internally, recalibrate the roadmap and update stakeholders."
                ),
            },
        ],
    },
    "data_scientist": {
        "technical": [
            {
                "q": "How do you handle class imbalance in a classification problem?",
                "a": (
                    "Techniques by priority: 1) Collect more minority-class data. 2) Use stratified sampling. "
                    "3) Apply SMOTE or ADASYN for synthetic oversampling. 4) Use class weights in the loss function. "
                    "5) Try anomaly detection framing. 6) Evaluate with precision-recall AUC, not accuracy. "
                    "Choice depends on dataset size and domain constraints."
                ),
            },
            {
                "q": "Explain the bias-variance tradeoff and how it affects model selection.",
                "a": (
                    "High bias = underfitting (model too simple, misses patterns). "
                    "High variance = overfitting (model memorizes noise, fails on new data). "
                    "The sweet spot minimizes total error. Regularization (L1/L2), cross-validation, "
                    "and ensemble methods (bagging reduces variance, boosting reduces bias) help navigate the tradeoff."
                ),
            },
        ],
        "situational": [
            {
                "q": "A stakeholder asks you to build a model but the data quality is poor. How do you proceed?",
                "a": (
                    "Document specific data quality issues (missing values, inconsistencies, labeling errors). "
                    "Quantify impact: 'With current data, model accuracy ceiling is ~60%.' "
                    "Propose a data improvement plan with effort estimates. If timeline is fixed, "
                    "build a baseline model with caveats and iterate as data improves."
                ),
            },
        ],
    },
    "sales": {
        "technical": [
            {
                "q": "Walk me through your process for qualifying a lead.",
                "a": (
                    "I use MEDDPICC: Metrics (quantified business case), Economic Buyer (who signs), "
                    "Decision Criteria (what they evaluate), Decision Process (approval steps), "
                    "Paper Process (legal/procurement), Implicate Pain (why act now), "
                    "Champion (internal advocate), Competition (alternatives considered). "
                    "Disqualify early if key elements are missing."
                ),
            },
        ],
        "situational": [
            {
                "q": "A prospect goes silent after receiving your proposal. What's your approach?",
                "a": (
                    "Wait 3 business days, then send a value-add follow-up (relevant case study, not 'just checking in'). "
                    "If no response in a week, try a different channel (call, LinkedIn). "
                    "After 2 weeks, send a 'breakup email' creating urgency. "
                    "Throughout, engage the champion for internal intel on what's causing the delay."
                ),
            },
        ],
    },
    "marketing": {
        "technical": [
            {
                "q": "How would you measure the ROI of a content marketing campaign?",
                "a": (
                    "Track the funnel: impressions → clicks → leads → MQLs → SQLs → closed-won. "
                    "Attribution model: multi-touch (first-touch for awareness, last-touch for conversion). "
                    "Calculate CAC per channel. Compare content-sourced pipeline to paid pipeline. "
                    "Include SEO value: rank improvements, organic traffic growth, domain authority."
                ),
            },
        ],
        "situational": [
            {
                "q": "Your CEO wants to launch a campaign in 2 weeks but your team is at capacity. What do you do?",
                "a": (
                    "Present current workload with delivery dates. Ask the CEO to stack-rank: "
                    "what gets deprioritized for this campaign? Propose a lean version that's achievable in 2 weeks "
                    "vs. a full version in 4 weeks. If it's truly urgent, identify what can be outsourced "
                    "(freelancers, agencies) with budget implications."
                ),
            },
        ],
    },
    "finance": {
        "technical": [
            {
                "q": "How would you build a 3-statement financial model?",
                "a": (
                    "Start with the income statement: revenue drivers, COGS, opex. "
                    "Link net income to the cash flow statement via working capital changes, D&A, and capex. "
                    "Balance sheet balances via the cash line. Use historical data for assumptions, "
                    "scenario analysis (base/bull/bear) for projections. Circular reference for interest "
                    "requires iteration or a plug."
                ),
            },
        ],
        "situational": [
            {
                "q": "You find a material error in a financial report that's already been sent to the board. What do you do?",
                "a": (
                    "Immediately quantify the error's impact. Inform your manager and CFO within the hour. "
                    "Prepare a corrected version with a clear explanation of what changed and why. "
                    "Issue a formal correction to the board. Conduct a root-cause analysis "
                    "and add a review checkpoint to prevent recurrence."
                ),
            },
        ],
    },
    "consulting": {
        "technical": [
            {
                "q": "Walk me through how you'd structure a market entry case.",
                "a": (
                    "Framework: 1) Market attractiveness (size, growth, competition, regulations). "
                    "2) Company capabilities (core competencies, resources, brand transferability). "
                    "3) Entry strategy (organic build, acquisition, JV/partnership). "
                    "4) Financial viability (investment required, breakeven timeline, NPV). "
                    "Start with clarifying questions, then hypothesize and test each branch."
                ),
            },
        ],
        "situational": [
            {
                "q": "Your client disagrees with your analysis findings. How do you handle it?",
                "a": (
                    "Listen fully to understand their objection — is it data, methodology, or conclusion? "
                    "If data: validate together. If methodology: explain reasoning and offer alternatives. "
                    "If conclusion: present the evidence chain and ask what would change their mind. "
                    "Never be defensive. The goal is the right answer, not being right."
                ),
            },
        ],
    },
}

LEVEL_MODIFIERS = {
    "junior": {
        "prefix": "For an entry-level candidate: ",
        "focus": "fundamentals, eagerness to learn, teamwork",
    },
    "mid": {
        "prefix": "For a mid-level candidate: ",
        "focus": "independent execution, growing ownership, technical depth",
    },
    "senior": {
        "prefix": "For a senior candidate: ",
        "focus": "leadership, system design, cross-team impact, mentoring",
    },
    "staff": {
        "prefix": "For a staff-level candidate: ",
        "focus": "organizational impact, technical strategy, ambiguity navigation",
    },
}


class InterviewPrep:
    def __init__(self, role: str, company: str = "", level: str = "mid"):
        self.role = role.lower().replace(" ", "_")
        self.company = company
        self.level = level.lower()

    def generate_questions(self, count: int = 8) -> list[dict]:
        questions: list[InterviewQuestion] = []

        behavioral = random.sample(BEHAVIORAL_QUESTIONS, min(3, len(BEHAVIORAL_QUESTIONS)))
        for bq in behavioral:
            questions.append(InterviewQuestion(
                type="behavioral",
                question=bq["q"],
                model_answer=bq["a"],
                difficulty=self._map_difficulty(self.level),
            ))

        role_qs = ROLE_QUESTIONS.get(self.role, {})
        for qtype in ("technical", "situational"):
            pool = role_qs.get(qtype, [])
            selected = random.sample(pool, min(2, len(pool))) if pool else []
            for sq in selected:
                questions.append(InterviewQuestion(
                    type=qtype,
                    question=self._contextualize(sq["q"]),
                    model_answer=sq["a"],
                    difficulty=self._map_difficulty(self.level),
                ))

        if self.company:
            questions.append(InterviewQuestion(
                type="company_specific",
                question=f"Why do you want to work at {self.company}?",
                model_answer=(
                    f"Research {self.company}'s mission, recent product launches, and culture. "
                    f"Connect your skills and values to their specific needs. "
                    f"Reference a recent achievement or initiative that genuinely excites you."
                ),
                difficulty="easy",
            ))
            questions.append(InterviewQuestion(
                type="company_specific",
                question=f"What do you know about {self.company}'s products/services?",
                model_answer=(
                    f"Demonstrate deep research: mention {self.company}'s core products, "
                    f"target market, competitive positioning, and recent news. "
                    f"Show you understand their business model and where your role fits."
                ),
                difficulty="easy",
            ))

        random.shuffle(questions)
        return [
            {
                "type": q.type,
                "question": q.question,
                "model_answer": q.model_answer,
                "difficulty": q.difficulty,
            }
            for q in questions[:count]
        ]

    def _contextualize(self, question: str) -> str:
        if self.company:
            question = question.replace("a company", self.company).replace("your company", self.company)
        mod = LEVEL_MODIFIERS.get(self.level)
        if mod:
            question = f"{mod['prefix']}{question}"
        return question

    @staticmethod
    def _map_difficulty(level: str) -> str:
        return {"junior": "easy", "mid": "medium", "senior": "hard", "staff": "hard"}.get(level, "medium")

    @staticmethod
    def get_available_roles() -> list[str]:
        return sorted(ROLE_QUESTIONS.keys())
