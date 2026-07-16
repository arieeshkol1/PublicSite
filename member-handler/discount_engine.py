"""
Discount Engine - Pure-function module for custom subscription plan pricing.

Calculates discounted monthly price and token allocation based on
commitment period length and admin-configurable discount tiers.
"""

from decimal import Decimal, ROUND_HALF_UP


def calculate_discount(commitment_months: int, config: dict) -> dict:
    """Calculate discounted price and token allocation.

    Args:
        commitment_months: Number of months for commitment (3-24 inclusive).
        config: Discount configuration dictionary containing:
            - baseMonthlyPrice (Decimal or int/float): Base monthly price before discount.
            - baseTokenCount (int): Base monthly token allocation before bonus.
            - discountTiers (list): Sorted list of tier dicts, each with:
                - minMonths (int): Minimum months for this tier (inclusive).
                - maxMonths (int): Maximum months for this tier (inclusive).
                - discountPercent (int): Discount percentage for this tier.

    Returns:
        dict with keys:
            - monthlyPrice (Decimal): Discounted monthly price.
            - tokenAllocation (int): Increased token allocation.
            - discountPercent (int): Applied discount percentage.
            - commitmentMonths (int): The input commitment period.
            - totalCommitmentValue (Decimal): monthlyPrice * commitmentMonths.

    Raises:
        ValueError: If commitment_months is not an int or outside 3-24 range.
        ValueError: If no matching discount tier is found for the commitment period.
    """
    # Input validation
    if not isinstance(commitment_months, int):
        raise ValueError("commitment_months must be an integer")
    if commitment_months < 3 or commitment_months > 24:
        raise ValueError("commitment_months must be between 3 and 24 inclusive")

    # Extract config values
    base_monthly_price = Decimal(str(config['baseMonthlyPrice']))
    base_token_count = int(config['baseTokenCount'])
    discount_tiers = config['discountTiers']

    # Find matching tier
    discount_percent = None
    for tier in discount_tiers:
        min_months = int(tier['minMonths'])
        max_months = int(tier['maxMonths'])
        if min_months <= commitment_months <= max_months:
            discount_percent = int(tier['discountPercent'])
            break

    if discount_percent is None:
        raise ValueError(
            f"No discount tier found for commitment_months={commitment_months}"
        )

    # Calculate discounted monthly price
    # monthlyPrice = baseMonthlyPrice * (1 - discountPercent/100)
    discount_factor = Decimal(str(discount_percent)) / Decimal('100')
    monthly_price = base_monthly_price * (Decimal('1') - discount_factor)

    # Calculate token allocation
    # tokenAllocation = round(baseTokenCount * (1 + discountPercent/100))
    token_multiplier = 1 + discount_percent / 100
    token_allocation = round(base_token_count * token_multiplier)

    # Validate bounds
    # Price must be > 0
    if monthly_price <= Decimal('0'):
        monthly_price = Decimal('0.01')  # Floor at minimum positive value

    # Tokens must be >= baseTokenCount
    if token_allocation < base_token_count:
        token_allocation = base_token_count

    # Calculate total commitment value
    total_commitment_value = monthly_price * Decimal(str(commitment_months))

    return {
        'monthlyPrice': monthly_price,
        'tokenAllocation': token_allocation,
        'discountPercent': discount_percent,
        'commitmentMonths': commitment_months,
        'totalCommitmentValue': total_commitment_value,
    }
