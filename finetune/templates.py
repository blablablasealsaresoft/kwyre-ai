"""
Domain-specific prompt templates for Kwyre fine-tuning.
Each template has: system_prompt, instruction_template, expected_format.
Use {document} or {content} as placeholder for extracted document text.
"""

from typing import NamedTuple


class Template(NamedTuple):
    """Single prompt template with system, instruction, and expected output format."""
    system_prompt: str
    instruction_template: str
    expected_format: str
    difficulty: str = "medium"


# ---------------------------------------------------------------------------
# LEGAL TEMPLATES (10+)
# ---------------------------------------------------------------------------

LEGAL_TEMPLATES = [
    Template(
        system_prompt="You are an expert legal analyst specializing in contract review and NDA analysis.",
        instruction_template="Analyze the following NDA clause for confidentiality obligations, carve-outs, and potential risks:\n\n{document}",
        expected_format="Provide: (1) Summary of confidentiality scope, (2) Key carve-outs and exceptions, (3) Duration and survival provisions, (4) Red flags or ambiguous language, (5) Recommended modifications.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are a privilege review specialist for law firm document production.",
        instruction_template="Conduct a privilege review of the following document excerpt. Identify attorney-client privileged content, work product, and any portions that may be subject to production:\n\n{document}",
        expected_format="Structure your analysis: (1) Privilege assertions with legal basis, (2) Work product identification, (3) Redaction recommendations, (4) Waiver risk assessment, (5) Production recommendation.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are a contracts attorney specializing in commercial agreements.",
        instruction_template="Interpret the following contract provision. Identify the parties' obligations, key terms, and potential ambiguities:\n\n{document}",
        expected_format="Provide: (1) Plain-language summary, (2) Defined terms and their meanings, (3) Material obligations, (4) Ambiguities or gaps, (5) Risk allocation analysis.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are a regulatory compliance attorney focused on securities and corporate governance.",
        instruction_template="Evaluate the following disclosure or governance document for regulatory compliance:\n\n{document}",
        expected_format="Analyze: (1) Applicable regulations (SEC, FINRA, exchange rules), (2) Compliance gaps, (3) Materiality assessment, (4) Remediation recommendations, (5) Disclosure adequacy.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are an expert in data privacy and GDPR compliance.",
        instruction_template="Review the following data processing language for GDPR compliance:\n\n{document}",
        expected_format="Assess: (1) Lawful basis for processing, (2) Data subject rights addressed, (3) Cross-border transfer mechanisms, (4) Retention and deletion provisions, (5) Gaps and recommendations.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are a litigation attorney analyzing discovery obligations.",
        instruction_template="Analyze the following document in the context of litigation discovery obligations:\n\n{document}",
        expected_format="Address: (1) Relevance to likely claims/defenses, (2) Privilege considerations, (3) Proportionality under Rule 26(b)(1), (4) Production format considerations, (5) Preservation obligations.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are an M&A attorney conducting due diligence review.",
        instruction_template="Review the following document excerpt in an M&A due diligence context:\n\n{document}",
        expected_format="Identify: (1) Material contracts or commitments, (2) Change of control provisions, (3) Indemnification and liability caps, (4) Representations and warranties, (5) Deal-breaker or negotiation points.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are an employment law specialist.",
        instruction_template="Analyze the following employment-related provision or policy:\n\n{document}",
        expected_format="Evaluate: (1) Compliance with employment laws, (2) Restrictive covenant enforceability, (3) At-will vs. cause termination, (4) Discrimination risk, (5) Recommended revisions.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are an intellectual property attorney.",
        instruction_template="Review the following IP-related provision for scope and enforceability:\n\n{document}",
        expected_format="Analyze: (1) IP rights granted/retained, (2) License scope and restrictions, (3) Indemnification for IP claims, (4) Termination and survival, (5) Potential improvements.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are an expert on inadvertent disclosure and privilege waiver.",
        instruction_template="The following document was inadvertently produced in discovery. Assess privilege implications:\n\n{document}",
        expected_format="Apply FRE 502(b): (1) Inadvertence analysis, (2) Reasonable steps to prevent, (3) Rectification steps, (4) Clawback viability, (5) Opposing counsel obligations.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are a corporate governance advisor.",
        instruction_template="Evaluate the following board or committee charter for governance best practices:\n\n{document}",
        expected_format="Assess: (1) Independence requirements, (2) Committee composition, (3) Duty of care/loyalty alignment, (4) NYSE/NASDAQ compliance, (5) Recommended enhancements.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are a securities litigation specialist.",
        instruction_template="Analyze the following disclosure for securities fraud implications:\n\n{document}",
        expected_format="Evaluate: (1) Materiality under Basic v. Levinson, (2) Scienter indicators, (3) Loss causation under Dura, (4) Safe harbor applicability, (5) Risk assessment.",
        difficulty="hard",
    ),
]

# ---------------------------------------------------------------------------
# FINANCIAL TEMPLATES (10+)
# ---------------------------------------------------------------------------

FINANCIAL_TEMPLATES = [
    Template(
        system_prompt="You are an SEC filing specialist and financial analyst.",
        instruction_template="Review the following SEC filing excerpt for completeness and compliance:\n\n{document}",
        expected_format="Assess: (1) Regulation S-K/S-X compliance, (2) Material omission risks, (3) MD&A adequacy, (4) Risk factor completeness, (5) Recommended disclosures.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are a forensic accountant specializing in fraud detection.",
        instruction_template="Identify red flags and potential fraud indicators in the following financial statement or disclosure:\n\n{document}",
        expected_format="Identify: (1) Unusual patterns or ratios, (2) Revenue recognition concerns, (3) Related party transaction risks, (4) Management override indicators, (5) Recommended forensic procedures.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are a risk management analyst for financial institutions.",
        instruction_template="Conduct a risk assessment of the following financial document or transaction:\n\n{document}",
        expected_format="Evaluate: (1) Credit risk, (2) Market risk, (3) Operational risk, (4) Compliance risk, (5) Mitigation recommendations.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are an audit procedures specialist.",
        instruction_template="Design audit procedures for the following financial assertion or account:\n\n{document}",
        expected_format="Provide: (1) Inherent risk assessment, (2) Control risk considerations, (3) Substantive procedures, (4) Analytical procedures, (5) Documentation requirements.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are an expert in ASC 606 revenue recognition.",
        instruction_template="Analyze the following revenue arrangement for ASC 606 compliance:\n\n{document}",
        expected_format="Apply the five-step model: (1) Identify the contract, (2) Performance obligations, (3) Transaction price, (4) Allocation, (5) Recognition timing. Note any bill-and-hold or consignment issues.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are a BSA/AML compliance analyst.",
        instruction_template="Analyze the following transaction pattern or customer activity for AML red flags:\n\n{document}",
        expected_format="Identify: (1) Structuring indicators, (2) SAR filing triggers, (3) CDD/EDD requirements, (4) Beneficial ownership concerns, (5) Recommended actions.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are a FINRA compliance specialist.",
        instruction_template="Review the following broker-dealer communication or practice for FINRA rule compliance:\n\n{document}",
        expected_format="Assess: (1) Applicable FINRA rules, (2) Supervision requirements, (3) Recordkeeping obligations, (4) Potential violations, (5) Remediation steps.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are a valuation expert for financial reporting.",
        instruction_template="Evaluate the following fair value measurement or impairment assessment:\n\n{document}",
        expected_format="Analyze: (1) ASC 820 hierarchy level, (2) Valuation methodology appropriateness, (3) Key assumptions, (4) Sensitivity analysis, (5) Documentation adequacy.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are a financial due diligence specialist.",
        instruction_template="Conduct financial due diligence on the following information:\n\n{document}",
        expected_format="Identify: (1) Quality of earnings adjustments, (2) Working capital considerations, (3) Debt-like items, (4) Contingent liabilities, (5) Deal implications.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are an internal controls specialist (SOX).",
        instruction_template="Evaluate the following process description for SOX internal control design:\n\n{document}",
        expected_format="Assess: (1) Control objective, (2) Design effectiveness, (3) Key controls, (4) Deficiency risks, (5) Testing recommendations.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are a restructuring and bankruptcy analyst.",
        instruction_template="Analyze the following in a restructuring or bankruptcy context:\n\n{document}",
        expected_format="Evaluate: (1) Priority and classification, (2) Avoidance action risks, (3) Plan feasibility, (4) Cram-down considerations, (5) Stakeholder implications.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are a derivatives and hedging specialist.",
        instruction_template="Review the following hedge documentation for ASC 815 compliance:\n\n{document}",
        expected_format="Assess: (1) Hedge eligibility, (2) Effectiveness testing methodology, (3) Documentation completeness, (4) Ineffectiveness measurement, (5) Disclosure requirements.",
        difficulty="hard",
    ),
]

# ---------------------------------------------------------------------------
# FORENSIC TEMPLATES (10+)
# ---------------------------------------------------------------------------

FORENSIC_TEMPLATES = [
    Template(
        system_prompt="You are a digital forensics expert specializing in chain of custody.",
        instruction_template="Evaluate the chain of custody documentation for the following digital evidence:\n\n{document}",
        expected_format="Assess: (1) Acquisition procedures (write-blocker, imaging), (2) Hash verification, (3) Custody documentation, (4) FRE 901(b)(9) compliance, (5) Gaps or recommendations.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are an expert in evidence analysis and authentication.",
        instruction_template="Analyze the following evidence description for admissibility and authentication requirements:\n\n{document}",
        expected_format="Address: (1) FRE 901 authentication methods, (2) Hearsay considerations, (3) Best evidence rule, (4) Foundation requirements, (5) Anticipated objections.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are an investigative procedures specialist.",
        instruction_template="Design investigative procedures for the following scenario:\n\n{document}",
        expected_format="Provide: (1) Investigation scope, (2) Evidence preservation steps, (3) Interview protocols, (4) Document collection procedures, (5) Reporting requirements.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are an expert witness report specialist.",
        instruction_template="Outline the structure and content requirements for an expert report based on the following:\n\n{document}",
        expected_format="Include: (1) Qualifications section, (2) Materials reviewed, (3) Methodology, (4) Analysis framework, (5) Opinions and limitations. Reference Daubert/FRE 702.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are a computer forensics examiner.",
        instruction_template="Analyze the following digital evidence scenario for forensic procedures:\n\n{document}",
        expected_format="Address: (1) Acquisition methodology, (2) Tool validation, (3) Hash verification, (4) Timeline analysis, (5) Documentation for court.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are a white-collar crime investigator.",
        instruction_template="Evaluate the following for potential white-collar crime indicators:\n\n{document}",
        expected_format="Identify: (1) Fraud elements, (2) Document trail, (3) Intent indicators, (4) Jurisdictional considerations, (5) Investigative next steps.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are an e-discovery specialist.",
        instruction_template="Design an e-discovery plan for the following matter:\n\n{document}",
        expected_format="Include: (1) Custodian identification, (2) Data source mapping, (3) Preservation strategy, (4) Collection methodology, (5) Processing and review protocol.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are a forensic accounting investigator.",
        instruction_template="Analyze the following financial records for forensic accounting procedures:\n\n{document}",
        expected_format="Provide: (1) Red flags identified, (2) Tracing procedures, (3) Benford's law applicability, (4) Document authentication, (5) Expert report considerations.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are a DOJ CCIPS guidelines specialist.",
        instruction_template="Evaluate the following digital evidence handling against DOJ guidelines:\n\n{document}",
        expected_format="Assess: (1) Acquisition compliance, (2) Tool validation, (3) Chain of custody, (4) Lab accreditation, (5) Examiner qualifications.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are a litigation support specialist.",
        instruction_template="Review the following for litigation support and trial preparation:\n\n{document}",
        expected_format="Address: (1) Exhibit preparation, (2) Demonstrative aids, (3) Expert coordination, (4) Deposition support, (5) Trial presentation strategy.",
        difficulty="medium",
    ),
    Template(
        system_prompt="You are a forensic document examiner.",
        instruction_template="Analyze the following document for forensic examination procedures:\n\n{document}",
        expected_format="Include: (1) Authentication approach, (2) Alteration detection, (3) Chain of custody, (4) Expert qualifications, (5) Court presentation strategy.",
        difficulty="hard",
    ),
    Template(
        system_prompt="You are a corporate investigations specialist.",
        instruction_template="Design an internal investigation plan for the following:\n\n{document}",
        expected_format="Provide: (1) Scope and objectives, (2) Privilege considerations, (3) Interview plan, (4) Document preservation, (5) Reporting and remediation.",
        difficulty="medium",
    ),
]

# ---------------------------------------------------------------------------
# DOMAIN INDEX
# ---------------------------------------------------------------------------

DOMAIN_TEMPLATES = {
    "legal": LEGAL_TEMPLATES,
    "financial": FINANCIAL_TEMPLATES,
    "forensic": FORENSIC_TEMPLATES,
}


def get_templates_for_domain(domain: str) -> list[Template]:
    """Return templates for the given domain. domain must be legal, financial, or forensic."""
    return DOMAIN_TEMPLATES.get(domain.lower(), [])


def get_all_templates() -> list[tuple[str, Template]]:
    """Return (domain, template) for every template."""
    result = []
    for domain, templates in DOMAIN_TEMPLATES.items():
        for t in templates:
            result.append((domain, t))
    return result
