import numpy as np
from decimal import Decimal

def detect_unusual_spending(category, amount, user):
    """
    Detects if a given amount is unusually high for a user in a specific category.
    Returns a dictionary with the insight results.
    """
    # Import here to avoid circular imports if used in models or early during setup
    from .models import Transaction

    result = {
        "is_unusual": False,
        "z_score": 0.0,
        "category_mean": 0.0,
        "category_std": 0.0
    }

    # If category is None, we can't do category-specific stats easily
    if not category:
        return result

    try:
        amount_float = float(amount)
    except (TypeError, ValueError):
        return result

    # Query past expense transactions for this user and category
    past_transactions = Transaction.objects.filter(
        user=user,
        category=category,
        type=Transaction.TransactionType.EXPENSE
    ).values_list('amount', flat=True)
    
    # We need at least 5 past transactions to have a meaningful statistical baseline
    if len(past_transactions) < 5:
        return result

    past_amounts = [float(a) for a in past_transactions if a is not None]

    if not past_amounts:
        return result

    mean = np.mean(past_amounts)
    std = np.std(past_amounts)

    result["category_mean"] = round(float(mean), 2)
    result["category_std"] = round(float(std), 2)

    # If standard deviation is 0, it means all past transactions were the exact same amount.
    # In this case, we can flag any deviation, but to be safe with division by zero, we handle it.
    if std == 0:
        if amount_float > mean:
             # Flag as unusual if it's strictly greater and std is 0
             result["is_unusual"] = True
             result["z_score"] = float('inf')
        return result

    z_score = (amount_float - mean) / std
    result["z_score"] = round(float(z_score), 2)

    # Flag as unusual if z-score > 2 (unusually high). We don't flag unusually low spending as "unusual" in this context.
    if z_score > 2:
        result["is_unusual"] = True

    return result
