def detect_event(company: dict) -> str | None:
    """
    Detect corporate event type from company data.
    Returns event name matching a rule's 'event' field, or None.
    Checks the nature_of_company field directly for structural events,
    and recent_news for transactional events.
    """

    # TC-11.2: Subsidiary record detection — based on field value, not news
    nature = (company.get("nature_of_company") or "").strip()
    if "subsidiary" in nature.lower():
        return "subsidiary_record"

    news = (company.get("recent_news") or "").lower()

    # IPO detection
    if "ipo" in news or "listed on" in news:
        return "ipo_transition"

    # Bankruptcy detection
    if "bankruptcy" in news or "ceased operations" in news:
        return "bankruptcy_or_closure"

    # Acquisition detection
    if "acquired" in news or "acquisition" in news or "subsidiary" in news:
        return "post_cutoff_acquisition"

    # Merger detection
    if "merged" in news or "merger" in news:
        return "post_cutoff_merger"

    # Spin-off detection
    if "spin off" in news or "spun off" in news:
        return "spin_off_creation"

    # Layoff / restructuring (also catches TC-10.5.2 "reduces workforce")
    if "layoff" in news or "workforce reduction" in news or "restructuring" in news or "reduces workforce" in news:
        return "layoff_or_restructuring"

    # HQ relocation
    if "moved headquarters" in news or "relocated" in news:
        return "hq_relocation"

    # Rebranding
    if "rebranded" in news or "renamed" in news:
        return "corporate_rebranding"

    # TC-10.5.1: Legal scandal / regulatory controversy
    if "sec fine" in news or "sec " in news or "lawsuit" in news or "fraud" in news \
            or "misleading" in news or "bribery" in news or "scandal" in news \
            or "fine for" in news or "penalty" in news or "regulatory action" in news:
        return "legal_scandal_or_controversy"

    # TC-10.5.3: Crisis / data breach event
    if "data breach" in news or "cyber attack" in news or "hacked" in news \
            or "exposed" in news or "leaked" in news or "user data" in news:
        return "crisis_event"

    # TC-10.5.4: Active disruption — broad catch-all for negative events
    if "crisis" in news or "investigation" in news or "major disruption" in news \
            or "regulatory scrutiny" in news or "under probe" in news:
        return "active_disruption"

    # Market shift / disruption  (TC-10.3)
    if "disrupting" in news or "market shift" in news or "expansion" in news or "market" in news:
        return "market_shift_or_disruption"

    return None
