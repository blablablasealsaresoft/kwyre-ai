from __future__ import annotations

from dataclasses import dataclass

SE_TAX_RATE = 0.153
SE_TAX_INCOME_CAP = 168600  # 2024 Social Security wage base
MEDICARE_SURTAX_THRESHOLD = 200000
MEDICARE_SURTAX_RATE = 0.009
CCORP_FLAT_RATE = 0.21
QUALIFIED_DIVIDEND_RATE = 0.15  # long-term capital gains rate for qualified dividends
QBI_DEDUCTION_RATE = 0.20

FEDERAL_BRACKETS_2024_SINGLE = [
    (11600, 0.10),
    (47150, 0.12),
    (100525, 0.22),
    (191950, 0.24),
    (243725, 0.32),
    (609350, 0.35),
    (float("inf"), 0.37),
]


@dataclass
class EntityResult:
    entity_type: str
    gross_income: float
    business_expenses: float
    net_income: float
    owner_salary: float
    federal_income_tax: float
    self_employment_tax: float
    corporate_tax: float
    dividend_tax: float
    total_tax: float
    effective_rate: float
    se_tax_savings_vs_sole_prop: float
    notes: list[str]


def _income_tax(taxable: float) -> float:
    if taxable <= 0:
        return 0.0
    tax = 0.0
    prev = 0.0
    for ceiling, rate in FEDERAL_BRACKETS_2024_SINGLE:
        bracket_income = min(taxable, ceiling) - prev
        if bracket_income <= 0:
            break
        tax += bracket_income * rate
        prev = ceiling
    return tax


def _se_tax(net_se_income: float) -> float:
    taxable_se = net_se_income * 0.9235  # IRS adjustment
    ss_portion = min(taxable_se, SE_TAX_INCOME_CAP) * 0.124
    medicare_portion = taxable_se * 0.029
    surtax = max(0, taxable_se - MEDICARE_SURTAX_THRESHOLD) * MEDICARE_SURTAX_RATE
    return ss_portion + medicare_portion + surtax


def _calc_sole_prop(gross: float, expenses: float, _salary: float) -> EntityResult:
    net = gross - expenses
    se = _se_tax(net)
    se_deduction = se / 2
    taxable = net - se_deduction
    income_tax = _income_tax(taxable)

    return EntityResult(
        entity_type="Sole Proprietorship",
        gross_income=gross,
        business_expenses=expenses,
        net_income=net,
        owner_salary=net,
        federal_income_tax=round(income_tax, 2),
        self_employment_tax=round(se, 2),
        corporate_tax=0.0,
        dividend_tax=0.0,
        total_tax=round(income_tax + se, 2),
        effective_rate=round((income_tax + se) / net * 100, 2) if net > 0 else 0.0,
        se_tax_savings_vs_sole_prop=0.0,
        notes=["All net income subject to self-employment tax",
               "Simplest structure — no separate entity filing"],
    )


def _calc_llc(gross: float, expenses: float, _salary: float) -> EntityResult:
    net = gross - expenses
    qbi = net * QBI_DEDUCTION_RATE
    se = _se_tax(net)
    se_deduction = se / 2
    taxable = net - se_deduction - qbi
    income_tax = _income_tax(taxable)

    sole_prop = _calc_sole_prop(gross, expenses, _salary)

    return EntityResult(
        entity_type="LLC (Single-Member, Pass-Through)",
        gross_income=gross,
        business_expenses=expenses,
        net_income=net,
        owner_salary=net,
        federal_income_tax=round(income_tax, 2),
        self_employment_tax=round(se, 2),
        corporate_tax=0.0,
        dividend_tax=0.0,
        total_tax=round(income_tax + se, 2),
        effective_rate=round((income_tax + se) / net * 100, 2) if net > 0 else 0.0,
        se_tax_savings_vs_sole_prop=round(sole_prop.total_tax - (income_tax + se), 2),
        notes=[
            "Pass-through taxation — same as sole prop but with liability protection",
            f"QBI deduction of ${qbi:,.0f} reduces taxable income",
            "Self-employment tax still applies to all net income",
        ],
    )


def _calc_scorp(gross: float, expenses: float, salary: float) -> EntityResult:
    net = gross - expenses
    reasonable_salary = min(salary, net) if salary > 0 else net * 0.6
    distribution = max(0, net - reasonable_salary)

    payroll_employer = reasonable_salary * 0.0765
    payroll_employee = reasonable_salary * 0.0765
    total_payroll = payroll_employer + payroll_employee

    qbi = distribution * QBI_DEDUCTION_RATE
    taxable = reasonable_salary + distribution - qbi
    income_tax = _income_tax(taxable)

    sole_prop = _calc_sole_prop(gross, expenses, salary)

    return EntityResult(
        entity_type="S-Corporation",
        gross_income=gross,
        business_expenses=expenses,
        net_income=net,
        owner_salary=round(reasonable_salary, 2),
        federal_income_tax=round(income_tax, 2),
        self_employment_tax=round(total_payroll, 2),
        corporate_tax=0.0,
        dividend_tax=0.0,
        total_tax=round(income_tax + total_payroll, 2),
        effective_rate=round((income_tax + total_payroll) / net * 100, 2) if net > 0 else 0.0,
        se_tax_savings_vs_sole_prop=round(sole_prop.total_tax - (income_tax + total_payroll), 2),
        notes=[
            f"Reasonable salary: ${reasonable_salary:,.0f} (subject to payroll tax)",
            f"Distribution: ${distribution:,.0f} (avoids self-employment tax)",
            f"Payroll tax only on salary — saves SE tax on distributions",
            f"QBI deduction of ${qbi:,.0f} on pass-through distribution",
        ],
    )


def _calc_ccorp(gross: float, expenses: float, salary: float) -> EntityResult:
    net = gross - expenses
    reasonable_salary = min(salary, net) if salary > 0 else net * 0.5
    corp_taxable = net - reasonable_salary
    corp_tax = corp_taxable * CCORP_FLAT_RATE

    after_corp_tax = corp_taxable - corp_tax
    dividend_tax = after_corp_tax * QUALIFIED_DIVIDEND_RATE

    payroll_employer = reasonable_salary * 0.0765
    payroll_employee = reasonable_salary * 0.0765
    total_payroll = payroll_employer + payroll_employee

    personal_taxable = reasonable_salary + after_corp_tax
    personal_income_tax = _income_tax(reasonable_salary)

    total = personal_income_tax + total_payroll + corp_tax + dividend_tax
    sole_prop = _calc_sole_prop(gross, expenses, salary)

    return EntityResult(
        entity_type="C-Corporation",
        gross_income=gross,
        business_expenses=expenses,
        net_income=net,
        owner_salary=round(reasonable_salary, 2),
        federal_income_tax=round(personal_income_tax, 2),
        self_employment_tax=round(total_payroll, 2),
        corporate_tax=round(corp_tax, 2),
        dividend_tax=round(dividend_tax, 2),
        total_tax=round(total, 2),
        effective_rate=round(total / net * 100, 2) if net > 0 else 0.0,
        se_tax_savings_vs_sole_prop=round(sole_prop.total_tax - total, 2),
        notes=[
            f"Flat 21% corporate tax on ${corp_taxable:,.0f} retained earnings",
            f"Qualified dividends taxed at {QUALIFIED_DIVIDEND_RATE:.0%} on ${after_corp_tax:,.0f}",
            "Double taxation: corporate level + shareholder level",
            "May benefit from retained earnings strategy at scale",
        ],
    )


def compare_entities(
    gross_income: float,
    business_expenses: float,
    owner_salary: float = 0,
) -> list[EntityResult]:
    return [
        _calc_sole_prop(gross_income, business_expenses, owner_salary),
        _calc_llc(gross_income, business_expenses, owner_salary),
        _calc_scorp(gross_income, business_expenses, owner_salary),
        _calc_ccorp(gross_income, business_expenses, owner_salary),
    ]
