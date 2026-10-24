"""Public competition names transcribed from headings in the historic sheet.

No judge records or private documents from that sheet are included here.
"""

CATEGORIES = {
    "arts": ("Arts", [
        "2D Art", "3D Art", "Fashion Design", "Digital Art", "Photography",
        "Extemporaneous Drawing",
    ]),
    "knowledge-quran": ("Knowledge & Quran", [
        "Knowledge", "Brother's Quran Recitation & Memorization",
        "Sister's Quran Recitation & Memorization",
    ]),
    "writing-oratory": ("Writing & Oratory", [
        "Extemporaneous Essay", "Extemporaneous Speaking", "Prepared Essay",
        "Poetry", "Original Oratory", "Short Fiction", "Spoken Word",
    ]),
    "brackets": ("Brackets", [
        "Debate", "Brother's Improv", "Sister's Improv", "MIST Bowl",
    ]),
    "group-projects": ("Group Projects", [
        "Business Venture", "Brother's Nasheed", "Sister's Nasheed", "Short Film",
        "Humanitarian Service", "Science Fair", "Social Media",
    ]),
    "sports-referees": ("Sports Referees", [
        "Brother's Basketball", "Sister's Basketball", "Brother's Soccer",
        "Sister's Soccer",
    ]),
}


def category_name(slug):
    return CATEGORIES.get(slug, (None,))[0]
