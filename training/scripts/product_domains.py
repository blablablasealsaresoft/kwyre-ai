"""
KWYRE — Product-to-Domain Mapping

Maps each Mint Rail product to its primary training domain adapter.
Used by train_all_products.sh to route training to the correct domain.
"""

PRODUCT_DOMAINS = {
    "quantedge":      "financial_trading",
    "labmind":        "scientific_research",
    "dentai":         "dental_clinical",
    "codeforge":      "software_engineering",
    "taxshield":      "legal_compliance",
    "launchpad":      "career_placement",
    "soulsync":       "relationship_matching",
    "nfl-playcaller": "sports_analytics",
    "marchmind":      "college_basketball",
}

ALL_DOMAINS = [
    "legal_compliance",
    "insurance_actuarial",
    "healthcare_lifesciences",
    "defense_intelligence",
    "financial_trading",
    "blockchain_crypto",
    "sports_analytics",
    "relationship_matching",
    "software_engineering",
    "scientific_research",
    "career_placement",
    "college_basketball",
    "dental_clinical",
]

if __name__ == "__main__":
    print(f"Products: {len(PRODUCT_DOMAINS)}")
    for product, domain in PRODUCT_DOMAINS.items():
        print(f"  {product:20s} -> {domain}")
    print(f"\nAll domains ({len(ALL_DOMAINS)}):")
    for d in ALL_DOMAINS:
        products = [p for p, dom in PRODUCT_DOMAINS.items() if dom == d]
        tag = f" <- {', '.join(products)}" if products else ""
        print(f"  {d}{tag}")
