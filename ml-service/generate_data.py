import random

random.seed(42)

TEMPLATES = {
    "Food": (
        ["zomato order", "swiggy dinner", "dominos pizza", "starbucks coffee",
         "chai tapri", "restaurant bill", "mcdonalds burger", "bigbasket groceries",
         "lunch with friends", "cafe coffee day"],
        (80, 1500),
    ),
    "Transport": (
        ["uber ride", "ola cab", "petrol pump", "metro recharge", "bus pass",
         "rapido bike", "fastag toll", "auto rickshaw", "irctc train ticket",
         "parking fee"],
        (30, 2500),
    ),
    "Shopping": (
        ["amazon order", "flipkart purchase", "myntra clothes", "zara shirt",
         "nike shoes", "ikea furniture", "croma headphones", "decathlon gear",
         "mall shopping", "gift for friend"],
        (200, 8000),
    ),
    "Bills": (
        ["electricity bill", "jio recharge", "airtel postpaid", "wifi broadband bill",
         "water bill", "gas cylinder", "dth recharge", "insurance premium",
         "credit card bill", "maintenance charges"],
        (150, 5000),
    ),
    "Entertainment": (
        ["netflix subscription", "spotify premium", "bookmyshow movie",
         "pvr tickets", "steam game", "concert ticket", "prime video",
         "youtube premium", "bowling night", "amusement park"],
        (100, 3000),
    ),
    "Health": (
        ["apollo pharmacy", "doctor consultation", "medplus medicines",
         "dental checkup", "gym membership", "lab test", "eye checkup",
         "protein supplements", "physiotherapy", "hospital bill"],
        (100, 6000),
    ),
    "Education": (
        ["udemy course", "coursera fee", "college fees", "book purchase",
         "exam registration", "coaching class", "stationery", "online workshop",
         "library fine", "tuition payment"],
        (100, 15000),
    ),
}