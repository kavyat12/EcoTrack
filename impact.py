from calendar import month_name
from datetime import date


ACTIVITY_TYPES = {
    # Illustrative averages; replace with a verified local factor set for formal reporting.
    "car": {"label": "Car travel", "unit": "km", "factor": 0.192},
    "bus": {"label": "Bus travel", "unit": "km", "factor": 0.105},
    "electricity": {"label": "Electricity", "unit": "kWh", "factor": 0.4},
    "flight": {"label": "Air travel", "unit": "passenger-km", "factor": 0.15},
}

MATERIAL_GUIDANCE = {
    "Recyclables": "Rinse containers, keep paper dry, and check local rules for plastics.",
    "Organic": "Keep food scraps separate; composting can reduce landfill methane.",
    "Hazardous": "Never put batteries, paint, or chemicals in regular bins. Use a collection point.",
    "General waste": "Choose reusable products and separate anything accepted for recycling.",
    "Electronic": "Wipe personal data and use a certified e-waste drop-off, not a household bin.",
}


def month_keys(count=6, today=None):
    current = today or date.today()
    year, month = current.year, current.month
    months = []
    for offset in range(count - 1, -1, -1):
        index = year * 12 + month - 1 - offset
        item_year, item_month = divmod(index, 12)
        item_month += 1
        months.append(
            {
                "key": f"{item_year:04d}-{item_month:02d}",
                "label": month_name[item_month][:3],
            }
        )
    return months


def sustainability_score(month_emissions, diversion_rate, has_activity):
    if not has_activity:
        return None
    emissions_points = max(0, 70 * (1 - min(month_emissions, 100) / 100))
    diversion_points = min(max(diversion_rate, 0), 100) * 0.3
    return round(min(100, emissions_points + diversion_points))


def recommendations(month_emissions, diversion_rate, top_waste_category, has_activity):
    ideas = []
    if not has_activity:
        ideas.append(
            {
                "title": "Start with one small log",
                "detail": "Record a week of household waste or a commute to establish your personal baseline.",
                "action": "Log an activity",
            }
        )
    if diversion_rate < 40:
        ideas.append(
            {
                "title": "Give recyclables a second life",
                "detail": "Separate clean paper, glass, and accepted containers before they reach the general bin.",
                "action": "Explore recycling",
            }
        )
    if top_waste_category == "Organic":
        ideas.append(
            {
                "title": "Try a food-scrap plan",
                "detail": "Plan meals, store leftovers visibly, and compost suitable food scraps where available.",
                "action": "Log household waste",
            }
        )
    if month_emissions >= 100:
        ideas.append(
            {
                "title": "Look for a lower-carbon trip",
                "detail": "For one short car journey this week, consider walking, cycling, carpooling, or transit.",
                "action": "Log a carbon activity",
            }
        )
    if not any(item["title"] == "Try a food-scrap plan" for item in ideas):
        ideas.append(
            {
                "title": "Cut waste before it starts",
                "detail": "Carry a reusable bag or bottle and choose products with less packaging.",
                "action": "Log household waste",
            }
        )
    return ideas[:3]
